from __future__ import unicode_literals

import mock
from datetime import datetime
from decimal import Decimal, ROUND_UP

import balanced
import unittest
from psycopg2 import IntegrityError

from gittip import authentication, billing, testing
from gittip.billing.payday import FEE, MINIMUM


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


class TestBankAccount(testing.GittipBaseTest):

    @unittest.skip('TODO: write me')
    def test_balanced_bank_account(self):
        pass


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

    @unittest.skip('TODO: write me')
    def test_clear_bank_account(self):
        pass

    @unittest.skip('TODO: write me')
    def test_associate_bank_account(self):
        pass

    @unittest.skip('TODO: write me')
    def test_store_ach_error(self):
        pass


class TestBillingCharge(testing.GittipPaydayTest):
    def setUp(self):
        super(TestBillingCharge, self).setUp()
        self.participant_id = 'lgtest'
        self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
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

    @mock.patch('gittip.billing.payday.Payday.mark_missing_funding')
    def test_charge_without_balanced_customer_id(self, mpmf):
        result = self.payday.charge( self.participant_id
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

    @mock.patch('balanced.Account')
    def test_hit_balanced(self, ba):
        amount_to_charge = Decimal(10)  # $10.00 USD
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
        amount_to_charge = Decimal(0.06)  # $0.06 USD
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
        amount_to_charge = Decimal(0.06)  # $0.06 USD
        error_message = 'Woah, crazy'
        ba.find.side_effect = balanced.exc.HTTPError(error_message)
        charge_amount, fee, msg = self.payday.hit_balanced(
            self.participant_id,
            self.balanced_account_uri,
            amount_to_charge)
        self.assertEqual(msg, error_message)


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

            with self.assertRaises(ValueError):
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


class TestBillingPayouts(testing.GittipSettlementTest):
    def setUp(self):
        super(TestBillingPayouts, self).setUp()

        # let's create a couple of exchanges + participants so we can simulate
        # real life.
        participants = [
            ('claimed_recipient_without_balanced', None, None),
            ('claimed_recipient_no_merchant', 'no_merchant', None),
            ('claimed_recipient_no_bank_ac', 'merchant', None),
            ('claimed_recipient_with_bank_ac', 'merchant', '/v1/bank_ac'),
        ]

        for participant in participants:
            self._create_participant(*participant)
            for i in range(1, 3):
                self._create_exchange(participant[0], 3 * i, 0.5 * i)

    def _create_participant(self,
                            name,
                            account_uri=None,
                            destination_uri=None):
        INSERT_PARTICIPANT = '''
            insert into participants (
                id, pending, balance, balanced_account_uri,
                balanced_destination_uri
            ) values (
                %s, 0, 1, %s, %s
            )
        '''
        return self.db.execute(INSERT_PARTICIPANT,
                               (name, account_uri, destination_uri))

    def _create_exchange(self, particpant_id, amount, fee):
        return self.db.execute("""
            INSERT INTO exchanges (participant_id, amount, fee) VALUES (
                %s, %s, %s
            )
        """, (particpant_id, amount, fee))

    @mock.patch('gittip.billing.payday.balanced.Account')
    @mock.patch('gittip.billing.payday.balanced.Credit')
    def test_it_all(self, b_credit, b_account):
        """
        This runs the whole thing from end to end with minimal mocking.
        """
        accounts = []

        def find_account(account_uri):
            account = mock.Mock()
            accounts.append(account)
            if account_uri != 'merchant':
                account.roles = []
            else:
                account.roles = ['merchant']
            account.credit.return_value.created_at = datetime.utcnow()
            return account

        b_credit.query.filter.side_effect = balanced.exc.NoResultFound
        b_account.find = find_account

        self.settlement_manager.run()

        # two participants were merchants
        self.assertEqual(sum(a.credit.call_count for a in accounts), 2)

        self.settlement_manager.run()

        # second time we run should create no new calls to credit as we have
        # already market the exchanges as settled
        self.assertEqual(sum(a.credit.call_count for a in accounts), 2)

        recipients_who_should_be_settled = [
            'claimed_recipient_no_bank_ac', 'claimed_recipient_with_bank_ac'
        ]

        settled_recipients = list(self.db.fetchall('''
            SELECT participant_id, amount_in_cents
            FROM settlements
            WHERE settled IS NOT NULL
        '''))

        self.assertEqual(len(settled_recipients), 2)
        for participant in settled_recipients:
            self.assertIn(participant['participant_id'],
                          recipients_who_should_be_settled)
            self.assertEqual(participant['amount_in_cents'], 750)

    @mock.patch('gittip.billing.payday.balanced.Account')
    @mock.patch('gittip.billing.payday.balanced.Credit')
    def test_credit_settlement(self, b_credit, b_account):
        credit = mock.Mock()
        credit.created_at = datetime.utcnow()
        b_credit.query.filter.return_value.one.return_value = credit

        settlement_id = 999
        amount_in_cents = 500
        balanced_account_uri = '/v1/accounts/X'
        balanced_destination_uri = '/v1/bank_accounts/X'
        self.settlement_manager.cur = cursor = mock.Mock()
        account = mock.Mock()
        b_account.find.return_value = account

        cursor.rowcount = 2  # invalid

        args = (settlement_id,
                amount_in_cents,
                balanced_account_uri,
                balanced_destination_uri)

        with self.assertRaises(AssertionError):
            self.settlement_manager.credit_settlement(*args)

        cursor.rowcount = 1

        # should work fine, existing credit is returned and we mark as settled
        self.settlement_manager.credit_settlement(*args)

        _, kwargs = b_credit.query.filter.call_args
        self.assertEqual(kwargs, {'settlement_id': settlement_id})

        cursor_args, _ = cursor.execute.call_args
        self.assertEqual(cursor_args[1], (credit.created_at, settlement_id))

        # oh no, we will return
        b_credit.query.filter.side_effect = balanced.exc.NoResultFound()

        self.settlement_manager.credit_settlement(*args)

        credit_args, credit_kwargs = account.credit.call_args
        self.assertEqual(credit_args, (amount_in_cents,))
        self.assertItemsEqual(credit_kwargs, dict(
            destination_uri=balanced_destination_uri,
            meta_data={'settlement_id': settlement_id},
            description=u'Settlement {}'.format(settlement_id))
        )

    @mock.patch('gittip.billing.payday.balanced.Account')
    @mock.patch('gittip.billing.payday.SettleExchanges.'
                'get_exchanges_for_participant')
    @mock.patch('gittip.billing.payday.SettleExchanges.'
                'ask_participant_for_merchant_info')
    def test_create_settlement_for_exchanges(self,
                                             info_request,
                                             get_exchanges,
                                             b_account):

        get_exchanges.return_value = []
        account = mock.Mock()
        account.roles = ['merchant']
        account.bank_accounts.query.total = 0
        b_account.find.return_value = None
        participant_id = 'mjallday'
        balanced_account_uri = '/v1/accounts/X'
        self.settlement_manager.cur = cursor = mock.Mock()

        # no account found
        self.settlement_manager.create_settlement_for_exchanges(
            participant_id, balanced_account_uri)

        b_account.find.return_value = account

        # no bank accounts
        self.settlement_manager.create_settlement_for_exchanges(
            participant_id, balanced_account_uri)

        account.bank_accounts.query.total = 1
        account.roles.pop()

        # not a merchant
        self.settlement_manager.create_settlement_for_exchanges(
            participant_id, balanced_account_uri)

        account.roles = ['merchant']

        # everything passes
        self.settlement_manager.create_settlement_for_exchanges(
            participant_id, balanced_account_uri)

        self.assertEqual(info_request.call_count, 3)
        self.assertEqual(get_exchanges.call_count, 1)
        self.assertEqual(cursor.call_count, 0)

        exchanges = [
            {'exchange_id': 1, 'amount': Decimal('1.23'),
             'fee': Decimal('0.01')},
            {'exchange_id': 2, 'amount': Decimal('1.23'),
             'fee': Decimal('0.01')},
            {'exchange_id': 3, 'amount': Decimal('1.23'),
             'fee': Decimal('0.01')},
        ]

        get_exchanges.return_value = exchanges

        self.settlement_manager.create_settlement_for_exchanges(
            participant_id, balanced_account_uri)

        # amount was too low to trigger a settlement
        self.assertEqual(cursor.execute.call_count, 0)

        exchanges.append({
            'exchange_id': 4,
            'amount': Decimal('10.23'),
            'fee': Decimal('0.01')},
        )

        # setup db emulation
        cursor.fetchone.return_value = {'id': 1}
        cursor.rowcount = 3

        with self.assertRaises(AssertionError):
            self.settlement_manager.create_settlement_for_exchanges(
                participant_id, balanced_account_uri)

        self.assertEqual(cursor.execute.call_count, 2)

        cursor.reset_mock()
        cursor.rowcount = 4

        # this one will work OK
        self.settlement_manager.create_settlement_for_exchanges(
            participant_id, balanced_account_uri)

        self.assertEqual(cursor.execute.call_count, 2)

        # let's check the parameters we passed to the DB
        settlement_insert, _ = cursor.execute.call_args_list[0]
        exchange_update, _ = cursor.execute.call_args_list[1]

        _, args = settlement_insert
        self.assertEqual(args, ('mjallday', 1388))

        _, args = exchange_update
        self.assertEqual(args, (1, (1, 2, 3, 4)))
