from __future__ import unicode_literals
from datetime import datetime
import decimal
import mock
import unittest

import balanced

from gittip import authentication, billing

from tests import GittipBaseDBTest


class TestBilling(GittipBaseDBTest):
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


class TestBillingCharge(GittipBaseDBTest):
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
            from paydays
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


class TestBillingPayday(GittipBaseDBTest):
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
            from paydays
            where not exists (
                select *
                from paydays
                where ts_end='1970-01-01T00:00:00+00'::timestamptz
            )
        '''
        self.db.execute(insert)

    def _get_payday(self):
        select = '''
            select *
            from paydays
            where ts_end='1970-01-01T00:00:00+00'::timestamptz
        '''
        return self.db.fetchone(select)

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
