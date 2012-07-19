from __future__ import unicode_literals

import decimal
import mock
from datetime import datetime

import balanced
from gittip import authentication, billing, testing
from psycopg2 import IntegrityError


__author__ = 'marshall'


class TestCustomer(testing.GittipBaseTest):
    def setUp(self):
        super(TestCustomer, self).setUp()
        self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'

    @mock.patch('balanced.Account')
    def test_customer(self, ba):
        card = mock.Mock()
        card.last_four = '1234'
        card.expiration_month = 10
        card.expiration_year = 2020
        balanced_account = ba.find.return_value
        balanced_account.cards = [
            card,
        ]
        customer = billing.Customer(self.balanced_account_uri)
        self.assertEqual(customer['id'], balanced_account.uri)
        self.assertIn(card.last_four, customer['last4'])
        self.assertEqual(customer['expiry'], '10/2020')
        self.assertEqual(customer['nothing'], card.nothing)


class TestBilling(testing.GittipBaseDBTest):
    def setUp(self):
        super(TestBilling, self).setUp()
        self.participant_id = 'lgtest'
        self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
        self.card_uri = '/v1/marketplaces/M123/accounts/A123/cards/C123'
        billing.db = self.db

    @mock.patch('balanced.Account')
    def test_associate_valid(self, ba):
        not_found = balanced.exc.NoResultFound()
        ba.query.filter.return_value.one.side_effect = not_found
        ba.return_value.save.return_value.uri = self.balanced_account_uri

        # first time through, payment processor account is None
        billing.associate(self.participant_id, None, self.card_uri)

        expected_email_address = '{}@gittip.com'.format(
            self.participant_id
        )
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


class TestBillingCharge(testing.GittipBaseDBTest):
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

    @mock.patch('gittip.billing.mark_payday_missing_funding')
    def test_charge_without_balanced_customer_id(self, mpmf):
        result = billing.charge(self.participant_id, None, decimal.Decimal(1))
        self.assertFalse(result)
        self.assertEqual(mpmf.call_count, 1)

    @mock.patch('gittip.billing.charge_balanced_account')
    @mock.patch('gittip.billing.mark_payday_failed')
    def test_charge_failure(self, mpf, cba):
        cba.return_value = (None, None, 'FAILED')
        result = billing.charge(self.participant_id, self.balanced_account_uri,
                                decimal.Decimal(1))
        self.assertEqual(cba.call_count, 1)
        self.assertEqual(mpf.call_count, 1)
        self.assertFalse(result)

    @mock.patch('gittip.billing.charge_balanced_account')
    @mock.patch('gittip.billing.mark_payday_success')
    def test_charge_success(self, mps, cba):
        cba.return_value = (decimal.Decimal(1), decimal.Decimal(2), None)
        result = billing.charge(self.participant_id, self.balanced_account_uri,
                                decimal.Decimal(1))
        self.assertEqual(cba.call_count, 1)
        self.assertEqual(mps.call_count, 1)
        self.assertTrue(result)

    def test_mark_payday_missing_funding(self):
        query = '''
            select ncc_missing
            from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        '''
        res = self.db.fetchone(query)
        missing_count = res['ncc_missing']
        billing.mark_payday_missing_funding()
        res = self.db.fetchone(query)
        self.assertEqual(res['ncc_missing'], missing_count + 1)

    def test_mark_payday_failed(self):
        query = '''
            select ncc_failing
            from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        '''
        res = self.db.fetchone(query)
        fail_count = res['ncc_failing']
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            billing.mark_payday_failed(cur)
            cur.execute(query)
            res = cur.fetchone()
        self.assertEqual(res['ncc_failing'], fail_count + 1)

    def test_mark_payday_success(self):
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
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            billing.mark_payday_success(self.participant_id,
                                        amount, fee, charge_amount, cursor)
            # verify exchanges
            cursor.execute(exchange_sql, (amount, fee, self.participant_id))
            self.assertEqual(cursor.fetchone()['count'], 1)
            # verify paydays
            cursor.execute(payday_sql)
            self.assertEqual(cursor.fetchone()['nexchanges'], 1)

    @mock.patch('balanced.Account')
    def test_charge_balanced_account(self, ba):
        amount_to_charge = 10  # $10.00 USD
        expected_fee = (amount_to_charge + billing.FEE[0]) * billing.FEE[1]
        expected_fee = (amount_to_charge - expected_fee.quantize(
            billing.FEE[0], rounding=decimal.ROUND_UP)) * -1
        charge_amount, fee, msg = billing.charge_balanced_account(
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
    def test_charge_balanced_account_small_amount(self, ba):
        amount_to_charge = decimal.Decimal(0.06)  # $0.06 USD
        expected_fee = (amount_to_charge + billing.FEE[0]) * billing.FEE[1]
        expected_fee = (amount_to_charge - expected_fee.quantize(
            billing.FEE[0], rounding=decimal.ROUND_UP)) * -1
        expected_amount = billing.MINIMUM
        charge_amount, fee, msg = billing.charge_balanced_account(
            self.participant_id,
            self.balanced_account_uri,
            amount_to_charge)
        self.assertEqual(charge_amount, expected_amount)
        self.assertEqual(fee, expected_fee)
        customer = ba.find.return_value
        self.assertTrue(customer.debit.called_with(
            int(charge_amount * 100),
            self.participant_id
        ))

    @mock.patch('balanced.Account')
    def test_charge_balanced_account_failure(self, ba):
        amount_to_charge = decimal.Decimal(0.06)  # $0.06 USD
        error_message = 'Woah, crazy'
        ba.find.side_effect = balanced.exc.HTTPError(error_message)
        charge_amount, fee, msg = billing.charge_balanced_account(
            self.participant_id,
            self.balanced_account_uri,
            amount_to_charge)
        self.assertEqual(msg, error_message)


class TestBillingPayday(testing.GittipBaseDBTest):
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

    @mock.patch('gittip.billing.log')
    @mock.patch('gittip.billing.payday_one')
    def test_payday_loop(self, payday_one, log):
        participants = range(100)
        start = mock.Mock()
        billing.payday_loop(start, participants)

        self.assertEqual(log.call_count, 3)
        self.assertEqual(payday_one.call_count, len(participants))
        self.assertTrue(payday_one.called_with(start))

    def test_assert_one_payday(self):
        with self.assertRaises(AssertionError):
            billing.assert_one_payday(None)
        with self.assertRaises(AssertionError):
            billing.assert_one_payday([1, 2])

    @mock.patch('gittip.billing.get_tips_and_total')
    def test_payday_one_no_tips(self, get_tips_and_total):
        amount = decimal.Decimal(1.00)

        get_tips_and_total.return_value = [], amount
        payday_start = datetime.utcnow()
        participant = {
            'balance': 1,
            'id': self.participant_id,
            'balanced_account_uri': self.balanced_account_uri,
        }

        initial_payday = self._get_payday()
        billing.payday_one(payday_start, participant)
        resulting_payday = self._get_payday()

        self.assertEqual(initial_payday['ntippers'],
                         resulting_payday['ntippers'])
        self.assertEqual(initial_payday['ntips'],
                         resulting_payday['ntips'])
        self.assertEqual(initial_payday['nparticipants'] + 1,
                         resulting_payday['nparticipants'])

    @mock.patch('gittip.billing.get_tips_and_total')
    @mock.patch('gittip.billing.log_tip')
    def test_payday_one(self, log_tip, get_tips_and_total):
        amount = decimal.Decimal(1.00)
        like_a_tip = {
            'amount': amount,
            'tippee': 'mjallday',
            'ctime': datetime.utcnow(),
            'claimed_time': datetime.utcnow(),
        }

        # success, success, claimed, failure
        tips = [like_a_tip, like_a_tip, like_a_tip, like_a_tip]
        get_tips_and_total.return_value = tips, amount

        payday_start = datetime.utcnow()
        participant = {
            'balance': 1,
            'id': self.participant_id,
            'balanced_account_uri': self.balanced_account_uri,
        }

        return_values = [1, 1, 0, -1]
        return_values.reverse()

        def log_tip_return_values(*_):
            return return_values.pop()

        log_tip.side_effect = log_tip_return_values

        initial_payday = self._get_payday()
        billing.payday_one(payday_start, participant)
        resulting_payday = self._get_payday()

        self.assertEqual(initial_payday['ntippers'] + 1,
                         resulting_payday['ntippers'])
        self.assertEqual(initial_payday['ntips'] + 2,
                         resulting_payday['ntips'])
        self.assertEqual(initial_payday['nparticipants'] + 1,
                         resulting_payday['nparticipants'])

    @mock.patch('gittip.billing.get_tips_and_total')
    @mock.patch('gittip.billing.charge')
    def test_payday_one_short(self, charge, get_tips_and_total):
        amount = decimal.Decimal(1.00)
        like_a_tip = {
            'amount': amount,
            'tippee': 'mjallday',
            'ctime': datetime.utcnow(),
            'claimed_time': datetime.utcnow(),
        }

        # success, success, claimed, failure
        tips = [like_a_tip, like_a_tip, like_a_tip, like_a_tip]
        get_tips_and_total.return_value = tips, amount

        payday_start = datetime.utcnow()
        participant = {
            'balance': 0,
            'id': self.participant_id,
            'balanced_account_uri': self.balanced_account_uri,
        }

        # in real-life we wouldn't be able to catch an error as the charge
        # method will swallow any errors and return false. we don't handle this
        # return value within payday_one but instead continue on trying to
        # use the remaining credit in the user's account to payout as many tips
        # as possible.
        # here we're hacking the system and throwing the exception so execution
        # stops since we're only testing this part of the method. that smells
        # like we need to refactor.
        charge.side_effect = Exception()
        with self.assertRaises(Exception):
            billing.payday_one(payday_start, participant)
        self.assertTrue(charge.called_with(self.participant_id,
                                           self.balanced_account_uri,
                                           amount))

    @mock.patch('gittip.billing.transfer')
    @mock.patch('gittip.billing.log')
    def test_log_tip(self, log, transfer):
        amount = decimal.Decimal(1)
        invalid_amount = decimal.Decimal(0)
        tip = {
            'amount': amount,
            'tippee': self.participant_id,
            'claimed_time': datetime.utcnow(),
        }
        payday_start = datetime.utcnow()
        participant = {
            'id': 'mjallday',
        }
        result = billing.log_tip(participant, tip, payday_start)
        self.assertTrue(result)
        self.assertTrue(transfer.called_with(participant['id'],
                                             tip['tippee'],
                                             tip['amount']))
        self.assertTrue(log.called_with(
            'SUCCESS: $1 from mjallday to lgtest.'))

        # invalid amount
        tip['amount'] = invalid_amount
        result = billing.log_tip(participant, tip, payday_start)
        self.assertFalse(result)

        tip['amount'] = amount

        # not claimed
        tip['claimed_time'] = None
        result = billing.log_tip(participant, tip, payday_start)
        self.assertFalse(result)

        # claimed after payday
        tip['claimed_time'] = datetime.utcnow()
        result = billing.log_tip(participant, tip, payday_start)
        self.assertFalse(result)

        payday_start = datetime.utcnow()

        # transfer failed
        transfer.return_value = False
        result = billing.log_tip(participant, tip, payday_start)
        self.assertEqual(result, -1)

    @mock.patch('gittip.billing.log')
    def test_initialize_payday(self, log):
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

        participants, payday_start = billing.initialize_payday()

        expected_logging_call_args = [
            ('Starting a new payday.'),
            ('Payday started at {}.'.format(payday_start)),
            ('Zeroed out the pending column.'),
            ('Fetched participants.'),
        ]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            self.assertEqual(args[0], expected_logging_call_args.pop())

        log.reset_mock()
        # run a second time, we should see it pick up the existing payday
        second_participants, second_payday_start = billing.initialize_payday()

        self.assertEqual(payday_start, second_payday_start)
        participants = list(participants)
        second_participants = list(second_participants)

        # mahmoudimus is the only valid participant as he has a claimed time
        self.assertEqual(len(participants), 1)
        self.assertEqual(participants, second_participants)

        expected_logging_call_args = [
            ('Picking up with an existing payday.'),
            ('Payday started at {}.'.format(second_payday_start)),
            ('Zeroed out the pending column.'),
            ('Fetched participants.')]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            self.assertEqual(args[0], expected_logging_call_args.pop())

    @mock.patch('gittip.billing.log')
    def test_finish_payday(self, log):
        billing.finish_payday()
        self.assertTrue(log.called_with('Finished payday.'))

        # finishing the payday will set the ts_end date on this payday record
        # to now, so this will not return any result
        result = self.db.fetchone('''
            select * from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        ''')
        self.assertFalse(result)

    @mock.patch('gittip.billing.log')
    @mock.patch('gittip.billing.initialize_payday')
    @mock.patch('gittip.billing.payday_loop')
    @mock.patch('gittip.billing.finish_payday')
    def test_payday(self, finish, loop, init, log):
        participants = mock.Mock()
        payday_start = mock.Mock()
        init.return_value = (participants, payday_start)
        greeting = 'Greetings, program! It\'s PAYDAY!!!!'

        billing.payday()

        self.assertTrue(log.called_with(greeting))
        self.assertTrue(init.call_count)
        self.assertTrue(loop.called_with(init.return_value))
        self.assertTrue(finish.call_count)


class TestBillingTransfer(testing.GittipBaseDBTest):
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
        amount = decimal.Decimal(1)
        sender = 'test_transfer_sender'
        recipient = 'test_transfer_recipient'
        self._create_participant(sender)
        self._create_participant(recipient)

        result = billing.transfer(sender, recipient, amount)
        self.assertTrue(result)

        # no balance remaining for a second transfer
        result = billing.transfer(sender, recipient, amount)
        self.assertFalse(result)

    def test_debit_participant(self):
        amount = decimal.Decimal(1)
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

        with self.db.get_connection() as conn:
            cur = conn.cursor()

            billing.debit_participant(cur, participant, amount)
            conn.commit()

        final_amount = get_balance_amount(participant)
        self.assertEqual(initial_amount - amount, final_amount)

        # this will fail because not enough balance
        with self.db.get_connection() as conn:
            cur = conn.cursor()

            with self.assertRaises(ValueError):
                billing.debit_participant(cur, participant, amount)

    def test_credit_participant(self):
        amount = decimal.Decimal(1)
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

            billing.credit_participant(cur, recipient, amount)
            conn.commit()

        final_amount = get_pending_amount(recipient)
        self.assertEqual(initial_amount + amount, final_amount)

    def test_record_transfer(self):
        amount = decimal.Decimal(1)

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
                billing.record_transfer(cur,
                                        self.participant_id,
                                        recipient,
                                        amount)

            conn.commit()

        assert_transfer('jim', amount * 2)
        assert_transfer('kate', amount)
        assert_transfer('bob', amount)

    def test_record_transfer_invalid_participant(self):
        amount = decimal.Decimal(1)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            with self.assertRaises(IntegrityError):
                billing.record_transfer(cur, 'idontexist', 'nori', amount)

    def test_increment_payday(self):
        amount = decimal.Decimal(1)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            payday = self._get_payday(cur)
            billing.increment_payday(cur, amount)
            payday2 = self._get_payday(cur)

        self.assertEqual(payday['ntransfers'] + 1,
                         payday2['ntransfers'])
        self.assertEqual(payday['transfer_volume'] + amount,
                         payday2['transfer_volume'])
