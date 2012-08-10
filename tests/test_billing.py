from __future__ import unicode_literals

import mock
from datetime import datetime
from decimal import Decimal, ROUND_UP

import balanced
from gittip import authentication, billing, testing
from gittip.billing.payday import FEE, MINIMUM
from psycopg2 import IntegrityError
from aspen.utils import typecheck


__author__ = 'marshall'


class TestCard(testing.GittipBaseTest):
    def setUp(self):
        super(TestCard, self).setUp()
        self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
        self.stripe_customer_id = 'deadbeef'

    @mock.patch('balanced.Account')
    def test_balanced_card(self, ba):
        card = mock.Mock()
        card.last_four = 1234
        card.expiration_month = 10
        card.expiration_year = 2020
        card.street_address = "123 Main Street"
        card.meta = {"address_2": "Box 2"}
        card.region = "Confusion"
        card.postal_code = "90210"

        balanced_account = ba.find.return_value
        balanced_account.uri = self.balanced_account_uri
        balanced_account.cards = [card]

        card = billing.BalancedCard(self.balanced_account_uri)

        self.assertEqual(card['id'], '/v1/marketplaces/M123/accounts/A123')
        self.assertEqual(card['last_four'], 1234)
        self.assertEqual(card['last4'], '************1234')
        self.assertEqual(card['expiry'], '10/2020')
        self.assertEqual(card['address_1'], '123 Main Street')
        self.assertEqual(card['address_2'], 'Box 2')
        self.assertEqual(card['state'], 'Confusion')
        self.assertEqual(card['zip'], '90210')
        self.assertEqual(card['nothing'].__class__.__name__, mock.Mock.__name__)

    @mock.patch('stripe.Customer')
    def test_stripe_card(self, sc):
        active_card = {}
        active_card['last4'] = '1234'
        active_card['expiry_month'] = 10
        active_card['expiry_year'] = 2020
        active_card['address_line1'] = "123 Main Street"
        active_card['address_line2'] = "Box 2"
        active_card['address_state'] = "Confusion"
        active_card['address_zip'] = "90210"

        stripe_customer = sc.retrieve.return_value
        stripe_customer.id = self.stripe_customer_id
        stripe_customer.get = {'active_card': active_card}.get

        card = billing.StripeCard(self.stripe_customer_id)

        self.assertEqual(card['id'], 'deadbeef')
        self.assertEqual(card['last4'], "************1234")
        self.assertEqual(card['expiry'], '10/2020')
        self.assertEqual(card['address_1'], '123 Main Street')
        self.assertEqual(card['address_2'], 'Box 2')
        self.assertEqual(card['state'], 'Confusion')
        self.assertEqual(card['zip'], '90210')
        self.assertEqual(card['nothing'], '')


class TestBilling(testing.GittipPaydayTest):
    def setUp(self):
        super(TestBilling, self).setUp()
        self.participant_id = 'lgtest'
        self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
        self.card_uri = '/v1/marketplaces/M123/accounts/A123/cards/C123'
        billing.db = self.db

    def test_store_error_stores_error(self):
        billing.store_error("lgtest", "cheese is yummy")
        rec = self.db.fetchone("select * from participants where id='lgtest'")
        self.assertEqual(rec['last_bill_result'], "cheese is yummy")

    @mock.patch('balanced.Account')
    def test_associate_valid(self, ba):
        not_found = balanced.exc.NoResultFound()
        ba.query.filter.return_value.one.side_effect = not_found
        ba.return_value.save.return_value.uri = self.balanced_account_uri

        # first time through, payment processor account is None
        billing.associate(self.participant_id, None, self.card_uri)

        expected_email_address = '{}@gittip.com'.format(self.participant_id)
        _, kwargs = balanced.Account.call_args
        self.assertTrue(kwargs['email_address'], expected_email_address)

        user = authentication.User.from_id(self.participant_id)
        # participant in db should be updated
        self.assertEqual(user.session['balanced_account_uri'],
                         self.balanced_account_uri)

    @mock.patch('balanced.Account')
    def test_associate_invalid_card(self, ba):
        error_message = 'Something terrible'
        not_found = balanced.exc.HTTPError(error_message)
        ba.find.return_value.save.side_effect = not_found

        # second time through, payment processor account is balanced
        # account_uri
        billing.associate(self.participant_id, self.balanced_account_uri,
                          self.card_uri)
        user = authentication.User.from_id(self.participant_id)
        # participant in db should be updated to reflect the error message of
        # last update
        self.assertEqual(user.session['last_bill_result'], error_message)
        self.assertTrue(ba.find.call_count)

    @mock.patch('balanced.Account')
    def test_clear(self, ba):
        valid_card = mock.Mock()
        valid_card.is_valid = True
        invalid_card = mock.Mock()
        invalid_card.is_valid = False
        card_collection = [
            valid_card, invalid_card
        ]
        balanced.Account.find.return_value.cards = card_collection

        MURKY = """\

            UPDATE participants
               SET balanced_account_uri='not null'
                 , last_bill_result='ooga booga'
             WHERE id=%s

        """
        self.db.execute(MURKY, (self.participant_id,))

        billing.clear(self.participant_id, self.balanced_account_uri)

        self.assertFalse(valid_card.is_valid)
        self.assertTrue(valid_card.save.call_count)
        self.assertFalse(invalid_card.save.call_count)

        user = authentication.User.from_id(self.participant_id)
        self.assertFalse(user.session['last_bill_result'])
        self.assertFalse(user.session['balanced_account_uri'])


class TestBillingCharge(testing.GittipPaydayTest):
    def setUp(self):
        super(TestBillingCharge, self).setUp()
        self.participant_id = 'lgtest'
        self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
        self.stripe_customer_id = 'cus_deadbeef'
        self.tok = '/v1/marketplaces/M123/accounts/A123/cards/C123'
        billing.db = self.db
        # TODO: remove once we rollback transactions....
        insert = '''
            insert into paydays (
                ncc_failing, ts_end
            )
            select 0, '1970-01-01T00:00:00+00'::timestamptz
            where not exists (
                select *
                from paydays
                where ts_end='1970-01-01T00:00:00+00'::timestamptz
            )
        '''
        self.db.execute(insert)

    def prep(self, amount):
        """Given a dollar amount as a string, return a 3-tuple.

        The return tuple is like the one returned from _prep_hit, but with the
        second value, a log message, removed.

        """
        typecheck(amount, unicode)
        out = list(self.payday._prep_hit(Decimal(amount)))
        out = [out[0]] + out[2:]
        return tuple(out)


    @mock.patch('gittip.billing.payday.Payday.mark_missing_funding')
    def test_charge_without_balanced_customer_id_or_stripe_customer_id(self, mpmf):
        result = self.payday.charge( self.participant_id
                                   , None
                                   , None
                                   , Decimal(1)
                                    )
        self.assertFalse(result)
        self.assertEqual(mpmf.call_count, 1)

    @mock.patch('gittip.billing.payday.Payday.hit_balanced')
    @mock.patch('gittip.billing.payday.Payday.mark_failed')
    def test_charge_failure(self, mf, hb):
        hb.return_value = (None, None, 'FAILED')
        result = self.payday.charge( self.participant_id
                                   , self.balanced_account_uri
                                   , self.stripe_customer_id
                                   , Decimal(1)
                                    )
        self.assertEqual(hb.call_count, 1)
        self.assertEqual(mf.call_count, 1)
        self.assertFalse(result)

    @mock.patch('gittip.billing.payday.Payday.hit_balanced')
    @mock.patch('gittip.billing.payday.Payday.mark_success')
    def test_charge_success(self, ms, hb):
        hb.return_value = (Decimal(1), Decimal(2), None)
        result = self.payday.charge( self.participant_id
                                   , self.balanced_account_uri
                                   , self.stripe_customer_id
                                   , Decimal(1)
                                    )
        self.assertEqual(hb.call_count, 1)
        self.assertEqual(ms.call_count, 1)
        self.assertTrue(result)

    def test_mark_missing_funding(self):
        query = '''
            select ncc_missing
            from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        '''
        res = self.db.fetchone(query)
        missing_count = res['ncc_missing']
        self.payday.mark_missing_funding()
        res = self.db.fetchone(query)
        self.assertEqual(res['ncc_missing'], missing_count + 1)

    def test_mark_failed(self):
        query = '''
            select ncc_failing
            from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        '''
        res = self.db.fetchone(query)
        fail_count = res['ncc_failing']
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            self.payday.mark_failed(cur)
            cur.execute(query)
            res = cur.fetchone()
        self.assertEqual(res['ncc_failing'], fail_count + 1)

    def test_mark_success(self):
        amount = 1
        fee = 2
        charge_amount = 4
        exchange_sql = """
            select count(*)
            from exchanges
            where amount=%s
                and fee=%s
                and participant_id=%s
        """
        payday_sql = """
            select nexchanges
            from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        """
        with self.db.get_connection() as connection:
            cursor = connection.cursor()
            self.payday.mark_success(cursor, charge_amount, fee)

            # verify paydays
            cursor.execute(payday_sql)
            self.assertEqual(cursor.fetchone()['nexchanges'], 1)

    @mock.patch('stripe.Charge')
    def test_hit_stripe(self, ba):
        amount_to_charge = Decimal('10.00')  # $10.00 USD
        expected_fee = (amount_to_charge + FEE[0]) * FEE[1]
        expected_fee = (amount_to_charge - expected_fee.quantize(
            FEE[0], rounding=ROUND_UP)) * -1
        charge_amount, fee, msg = self.payday.hit_stripe(
            self.participant_id,
            self.stripe_customer_id,
            amount_to_charge)
        self.assertEqual(charge_amount, amount_to_charge + fee)
        self.assertEqual(fee, expected_fee)
        self.assertTrue(ba.find.called_with(self.stripe_customer_id))
        customer = ba.find.return_value
        self.assertTrue(customer.debit.called_with(
            int(charge_amount * 100),
            self.participant_id
        ))

    @mock.patch('balanced.Account')
    def test_hit_balanced(self, ba):
        amount_to_charge = Decimal('10.00')  # $10.00 USD
        expected_fee = (amount_to_charge + FEE[0]) * FEE[1]
        expected_fee = (amount_to_charge - expected_fee.quantize(
            FEE[0], rounding=ROUND_UP)) * -1
        charge_amount, fee, msg = self.payday.hit_balanced(
            self.participant_id,
            self.balanced_account_uri,
            amount_to_charge)
        self.assertEqual(charge_amount, amount_to_charge + fee)
        self.assertEqual(fee, expected_fee)
        self.assertTrue(ba.find.called_with(self.balanced_account_uri))
        customer = ba.find.return_value
        self.assertTrue(customer.debit.called_with(
            int(charge_amount * 100),
            self.participant_id
        ))

    @mock.patch('balanced.Account')
    def test_hit_balanced_small_amount(self, ba):
        amount_to_charge = Decimal('0.06')  # $0.06 USD
        expected_fee = (amount_to_charge + FEE[0]) * FEE[1]
        expected_fee = (amount_to_charge - expected_fee.quantize(
            FEE[0], rounding=ROUND_UP)) * Decimal('-1')
        expected_amount = MINIMUM
        charge_amount, fee, msg = \
                            self.payday.hit_balanced( self.participant_id
                                                    , self.balanced_account_uri
                                                    , amount_to_charge
                                                     )
        self.assertEqual(charge_amount, expected_amount)
        self.assertEqual(fee, expected_fee)
        customer = ba.find.return_value
        self.assertTrue(customer.debit.called_with(
            int(charge_amount * 100),
            self.participant_id
        ))

    @mock.patch('balanced.Account')
    def test_hit_balanced_failure(self, ba):
        amount_to_charge = Decimal('0.06')  # $0.06 USD
        error_message = 'Woah, crazy'
        ba.find.side_effect = balanced.exc.HTTPError(error_message)
        charge_amount, fee, msg = self.payday.hit_balanced(
            self.participant_id,
            self.balanced_account_uri,
            amount_to_charge)
        self.assertEqual(msg, error_message)


    # _prep_hit

    def test_prep_hit_basically_works(self):
        actual = self.payday._prep_hit(Decimal('20.00'))
        expected = ( 2110
                   , u'Charging %s 2110 cents ($20.00 + $1.10 fee = $21.10) on %s ... '
                   , Decimal('21.10')
                   , Decimal('1.10')
                    )
        assert actual == expected, actual


    def test_prep_hit_at_ten_dollars(self):
        actual = self.prep('10.00')
        expected = (1071, Decimal('10.71'), Decimal('0.71'))
        assert actual == expected, actual


    def test_prep_hit_at_forty_cents(self):
        actual = self.prep('0.40')
        expected = (1000, Decimal('10.00'), Decimal('0.33'))
        assert actual == expected, actual

    def test_prep_hit_at_fifty_cents(self):
        actual = self.prep('0.50')
        expected = (1000, Decimal('10.00'), Decimal('0.34'))
        assert actual == expected, actual

    def test_prep_hit_at_sixty_cents(self):
        actual = self.prep('0.60')
        expected = (1000, Decimal('10.00'), Decimal('0.34'))
        assert actual == expected, actual

    def test_prep_hit_at_eighty_cents(self):
        actual = self.prep('0.80')
        expected = (1000, Decimal('10.00'), Decimal('0.35'))
        assert actual == expected, actual


    def test_prep_hit_at_nine_thirty_one(self):
        actual = self.prep('9.31')
        expected = (1000, Decimal('10.00'), Decimal('0.68'))
        assert actual == expected, actual

    def test_prep_hit_at_nine_thirty_two(self):
        actual = self.prep('9.32')
        expected = (1000, Decimal('10.00'), Decimal('0.68'))
        assert actual == expected, actual

    def test_prep_hit_at_nine_thirty_three(self):
        actual = self.prep('9.33')
        expected = (1001, Decimal('10.01'), Decimal('0.68'))
        assert actual == expected, actual


class TestBillingPayday(testing.GittipPaydayTest):
    def setUp(self):
        super(TestBillingPayday, self).setUp()
        self.participant_id = 'lgtest'
        self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
        billing.db = self.db
        # TODO: remove once we rollback transactions....
        insert = '''
            insert into paydays (
                ncc_failing, ts_end
            )
            select 0, '1970-01-01T00:00:00+00'::timestamptz
            where not exists (
                select *
                from paydays
                where ts_end='1970-01-01T00:00:00+00'::timestamptz
            )
        '''
        self.db.execute(insert)

    def _get_payday(self):
        SELECT_PAYDAY = '''
            select *
            from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        '''
        return self.db.fetchone(SELECT_PAYDAY)

    @mock.patch('gittip.billing.payday.log')
    @mock.patch('gittip.billing.payday.Payday.charge_and_or_transfer')
    def test_loop(self, charge_and_or_transfer, log):
        participants = range(100)
        start = mock.Mock()
        self.payday.loop(start, participants)

        self.assertEqual(log.call_count, 3)
        self.assertEqual(charge_and_or_transfer.call_count, len(participants))
        self.assertTrue(charge_and_or_transfer.called_with(start))

    def test_assert_one_payday(self):
        with self.assertRaises(AssertionError):
            self.payday.assert_one_payday(None)
        with self.assertRaises(AssertionError):
            self.payday.assert_one_payday([1, 2])

    @mock.patch('gittip.billing.payday.get_tips_and_total')
    def test_charge_and_or_transfer_no_tips(self, get_tips_and_total):
        amount = Decimal(1.00)

        get_tips_and_total.return_value = [], amount
        ts_start = datetime.utcnow()
        participant = {
            'balance': 1,
            'id': self.participant_id,
            'balanced_account_uri': self.balanced_account_uri,
        }

        initial_payday = self._get_payday()
        self.payday.charge_and_or_transfer(ts_start, participant)
        resulting_payday = self._get_payday()

        self.assertEqual(initial_payday['ntippers'],
                         resulting_payday['ntippers'])
        self.assertEqual(initial_payday['ntips'],
                         resulting_payday['ntips'])
        self.assertEqual(initial_payday['nparticipants'] + 1,
                         resulting_payday['nparticipants'])

    @mock.patch('gittip.billing.payday.get_tips_and_total')
    @mock.patch('gittip.billing.payday.Payday.tip')
    def test_charge_and_or_transfer(self, tip, get_tips_and_total):
        amount = Decimal(1.00)
        like_a_tip = {
            'amount': amount,
            'tippee': 'mjallday',
            'ctime': datetime.utcnow(),
            'claimed_time': datetime.utcnow(),
        }

        # success, success, claimed, failure
        tips = [like_a_tip, like_a_tip, like_a_tip, like_a_tip]
        get_tips_and_total.return_value = tips, amount

        ts_start = datetime.utcnow()
        participant = {
            'balance': 1,
            'id': self.participant_id,
            'balanced_account_uri': self.balanced_account_uri,
        }

        return_values = [1, 1, 0, -1]
        return_values.reverse()

        def tip_return_values(*_):
            return return_values.pop()

        tip.side_effect = tip_return_values

        initial_payday = self._get_payday()
        self.payday.charge_and_or_transfer(ts_start, participant)
        resulting_payday = self._get_payday()

        self.assertEqual(initial_payday['ntippers'] + 1,
                         resulting_payday['ntippers'])
        self.assertEqual(initial_payday['ntips'] + 2,
                         resulting_payday['ntips'])
        self.assertEqual(initial_payday['nparticipants'] + 1,
                         resulting_payday['nparticipants'])

    @mock.patch('gittip.billing.payday.get_tips_and_total')
    @mock.patch('gittip.billing.payday.Payday.charge')
    def test_charge_and_or_transfer_short(self, charge, get_tips_and_total):
        amount = Decimal(1.00)
        like_a_tip = {
            'amount': amount,
            'tippee': 'mjallday',
            'ctime': datetime.utcnow(),
            'claimed_time': datetime.utcnow(),
        }

        # success, success, claimed, failure
        tips = [like_a_tip, like_a_tip, like_a_tip, like_a_tip]
        get_tips_and_total.return_value = tips, amount

        ts_start = datetime.utcnow()
        participant = {
            'balance': 0,
            'id': self.participant_id,
            'balanced_account_uri': self.balanced_account_uri,
        }


        # In real-life we wouldn't be able to catch an error as the charge
        # method will swallow any errors and return false. We don't handle this
        # return value within charge_and_or_transfer but instead continue on
        # trying to use the remaining credit in the user's account to payout as
        # many tips as possible.
        #
        # Here we're hacking the system and throwing the exception so execution
        # stops since we're only testing this part of the method. That smells
        # like we need to refactor.

        charge.side_effect = Exception()
        with self.assertRaises(Exception):
            billing.charge_and_or_transfer(ts_start, participant)
        self.assertTrue(charge.called_with(self.participant_id,
                                           self.balanced_account_uri,
                                           amount))

    @mock.patch('gittip.billing.payday.Payday.transfer')
    @mock.patch('gittip.billing.payday.log')
    def test_tip(self, log, transfer):
        amount = Decimal(1)
        invalid_amount = Decimal(0)
        tip = {
            'amount': amount,
            'tippee': self.participant_id,
            'claimed_time': datetime.utcnow(),
        }
        ts_start = datetime.utcnow()
        participant = {
            'id': 'mjallday',
        }
        result = self.payday.tip(participant, tip, ts_start)
        self.assertTrue(result)
        self.assertTrue(transfer.called_with(participant['id'],
                                             tip['tippee'],
                                             tip['amount']))
        self.assertTrue(log.called_with(
            'SUCCESS: $1 from mjallday to lgtest.'))

        # invalid amount
        tip['amount'] = invalid_amount
        result = self.payday.tip(participant, tip, ts_start)
        self.assertFalse(result)

        tip['amount'] = amount

        # not claimed
        tip['claimed_time'] = None
        result = self.payday.tip(participant, tip, ts_start)
        self.assertFalse(result)

        # claimed after payday
        tip['claimed_time'] = datetime.utcnow()
        result = self.payday.tip(participant, tip, ts_start)
        self.assertFalse(result)

        ts_start = datetime.utcnow()

        # transfer failed
        transfer.return_value = False
        result = self.payday.tip(participant, tip, ts_start)
        self.assertEqual(result, -1)

    @mock.patch('gittip.billing.payday.log')
    def test_start_zero_out_and_get_participants(self, log):
        # TODO: remove this once we have test db transactions
        self.db.execute('''
            delete from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        ''')

        PARTICIPANT_SQL = '''
            insert into participants (
                id, balance, balanced_account_uri, pending, claimed_time
            ) values (
                %s, %s, %s, %s, %s
            )
        '''

        participants = [
            ('whit537', 0, self.balanced_account_uri, None, None),
            ('mjallday', 10, self.balanced_account_uri, 1, None),
            ('mahmoudimus', 10, self.balanced_account_uri, 1,
             datetime.utcnow())
        ]

        for participant in participants:
            self.db.execute(PARTICIPANT_SQL, participant)

        ts_start = self.payday.start()
        self.payday.zero_out_pending()
        participants = self.payday.get_participants()

        expected_logging_call_args = [
            ('Starting a new payday.'),
            ('Payday started at {}.'.format(ts_start)),
            ('Zeroed out the pending column.'),
            ('Fetched participants.'),
        ]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            self.assertEqual(args[0], expected_logging_call_args.pop())

        log.reset_mock()

        # run a second time, we should see it pick up the existing payday
        second_ts_start = self.payday.start()
        self.payday.zero_out_pending()
        second_participants = self.payday.get_participants()

        self.assertEqual(ts_start, second_ts_start)
        participants = list(participants)
        second_participants = list(second_participants)

        # mahmoudimus is the only valid participant as he has a claimed time
        self.assertEqual(len(participants), 1)
        self.assertEqual(participants, second_participants)

        expected_logging_call_args = [
            ('Picking up with an existing payday.'),
            ('Payday started at {}.'.format(second_ts_start)),
            ('Zeroed out the pending column.'),
            ('Fetched participants.')]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            self.assertEqual(args[0], expected_logging_call_args.pop())

    @mock.patch('gittip.billing.payday.log')
    def test_end(self, log):
        self.payday.end()
        self.assertTrue(log.called_with('Finished payday.'))

        # finishing the payday will set the ts_end date on this payday record
        # to now, so this will not return any result
        result = self.db.fetchone('''
            select * from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        ''')
        self.assertFalse(result)

    @mock.patch('gittip.billing.payday.log')
    @mock.patch('gittip.billing.payday.Payday.start')
    @mock.patch('gittip.billing.payday.Payday.loop')
    @mock.patch('gittip.billing.payday.Payday.end')
    def test_payday(self, end, loop, init, log):
        participants = mock.Mock()
        ts_start = mock.Mock()
        init.return_value = (participants, ts_start)
        greeting = 'Greetings, program! It\'s PAYDAY!!!!'

        self.payday.run()

        self.assertTrue(log.called_with(greeting))
        self.assertTrue(init.call_count)
        self.assertTrue(loop.called_with(init.return_value))
        self.assertTrue(end.call_count)


class TestBillingTransfer(testing.GittipPaydayTest):
    def setUp(self):
        super(TestBillingTransfer, self).setUp()
        self.participant_id = 'lgtest'
        self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
        billing.db = self.db
        # TODO: remove once we rollback transactions....
        insert = '''
            insert into paydays (
                ncc_failing, ts_end
            )
            select 0, '1970-01-01T00:00:00+00'::timestamptz
            where not exists (
                select *
                from paydays
                where ts_end='1970-01-01T00:00:00+00'::timestamptz
            )
        '''
        self.db.execute(insert)

    def _get_payday(self, cursor):
        SELECT_PAYDAY = '''
            select *
            from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        '''
        cursor.execute(SELECT_PAYDAY)
        return cursor.fetchone()

    def _create_participant(self, name):
        INSERT_PARTICIPANT = '''
            insert into participants (
                id, pending, balance
            ) values (
                %s, 0, 1
            )
        '''
        return self.db.execute(INSERT_PARTICIPANT, (name,))

    def test_transfer(self):
        amount = Decimal(1)
        sender = 'test_transfer_sender'
        recipient = 'test_transfer_recipient'
        self._create_participant(sender)
        self._create_participant(recipient)

        result = self.payday.transfer(sender, recipient, amount)
        self.assertTrue(result)

        # no balance remaining for a second transfer
        result = self.payday.transfer(sender, recipient, amount)
        self.assertFalse(result)

    def test_debit_participant(self):
        amount = Decimal(1)
        participant = 'test_debit_participant'

        def get_balance_amount(participant):
            recipient_sql = '''
            select balance
            from participants
            where id = %s
            '''
            return self.db.fetchone(recipient_sql, (participant,))['balance']

        self._create_participant(participant)
        initial_amount = get_balance_amount(participant)

        with self.db.get_connection() as connection:
            cursor = connection.cursor()

            self.payday.debit_participant(cursor, participant, amount)
            connection.commit()

        final_amount = get_balance_amount(participant)
        self.assertEqual(initial_amount - amount, final_amount)

        # this will fail because not enough balance
        with self.db.get_connection() as conn:
            cur = conn.cursor()

            with self.assertRaises(IntegrityError):
                self.payday.debit_participant(cur, participant, amount)

    def test_credit_participant(self):
        amount = Decimal(1)
        recipient = 'test_credit_participant'

        def get_pending_amount(recipient):
            recipient_sql = '''
            select pending
            from participants
            where id = %s
            '''
            return self.db.fetchone(recipient_sql, (recipient,))['pending']

        self._create_participant(recipient)
        initial_amount = get_pending_amount(recipient)

        with self.db.get_connection() as conn:
            cur = conn.cursor()

            self.payday.credit_participant(cur, recipient, amount)
            conn.commit()

        final_amount = get_pending_amount(recipient)
        self.assertEqual(initial_amount + amount, final_amount)

    def test_record_transfer(self):
        amount = Decimal(1)

        # check with db that amount is what we expect
        def assert_transfer(recipient, amount):
            transfer_sql = '''
                select sum(amount) as sum
                from transfers
                where tippee = %s
            '''
            result = self.db.fetchone(transfer_sql, (recipient,))
            self.assertEqual(result['sum'], amount)

        recipients = [
            'jim', 'jim', 'kate', 'bob',
        ]
        seen = []

        for recipient in recipients:
            if not recipient in seen:
                self._create_participant(recipient)
                seen.append(recipient)

        with self.db.get_connection() as conn:
            cur = conn.cursor()

            for recipient in recipients:
                self.payday.record_transfer( cur
                                           , self.participant_id
                                           , recipient
                                           , amount
                                            )

            conn.commit()

        assert_transfer('jim', amount * 2)
        assert_transfer('kate', amount)
        assert_transfer('bob', amount)

    def test_record_transfer_invalid_participant(self):
        amount = Decimal(1)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            with self.assertRaises(IntegrityError):
                self.payday.record_transfer(cur, 'idontexist', 'nori', amount)

    def test_mark_transfer(self):
        amount = Decimal(1)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            payday = self._get_payday(cur)
            self.payday.mark_transfer(cur, amount)
            payday2 = self._get_payday(cur)

        self.assertEqual(payday['ntransfers'] + 1,
                         payday2['ntransfers'])
        self.assertEqual(payday['transfer_volume'] + amount,
                         payday2['transfer_volume'])
