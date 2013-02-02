from __future__ import unicode_literals

import balanced
import mock
from nose.tools import assert_equals, assert_raises

import gittip
from gittip import authentication, billing
from gittip.testing.harness import Harness


class TestBillingBase(Harness):
    balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
    balanced_destination_uri = '/v1/bank_accounts/X'
    card_uri = '/v1/marketplaces/M123/accounts/A123/cards/C123'

    def setUp(self):
        super(Harness, self).setUp()
        self.make_participant('alice')


class TestBalancedCard(Harness):
    balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'

    @mock.patch('balanced.Account')
    def test_balanced_card_basically_works(self, ba):
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
        balanced_account.cards = mock.Mock()
        balanced_account.cards.all.return_value = [card]

        expected = {
            'id': '/v1/marketplaces/M123/accounts/A123',
            'last_four': 1234,
            'last4': '************1234',
            'expiration_month': 10,
            'expiration_year': 2020,
            'address_1': '123 Main Street',
            'address_2': 'Box 2',
            'state': 'Confusion',
            'zip': '90210'
        }
        card = billing.BalancedCard(self.balanced_account_uri)
        actual = dict([(name, card[name]) for name in expected])
        assert_equals(actual, expected)

    @mock.patch('balanced.Account')
    def test_balanced_card_gives_class_name_instead_of_KeyError(self, ba):
        card = mock.Mock()

        balanced_account = ba.find.return_value
        balanced_account.uri = self.balanced_account_uri
        balanced_account.cards = mock.Mock()
        balanced_account.cards.all.return_value = [card]

        card = billing.BalancedCard(self.balanced_account_uri)

        expected = mock.Mock.__name__
        actual = card['nothing'].__class__.__name__
        assert_equals(actual, expected)


class TestStripeCard(Harness):
    @mock.patch('stripe.Customer')
    def test_stripe_card_basically_works(self, sc):
        active_card = {}
        active_card['last4'] = '1234'
        active_card['expiration_month'] = 10
        active_card['expiration_year'] = 2020
        active_card['address_line1'] = "123 Main Street"
        active_card['address_line2'] = "Box 2"
        active_card['address_state'] = "Confusion"
        active_card['address_zip'] = "90210"

        stripe_customer = sc.retrieve.return_value
        stripe_customer.id = 'deadbeef'
        stripe_customer.get = {'active_card': active_card}.get

        expected = {
            'id': 'deadbeef',
            'last4': '************1234',
            'expiration_month': 10,
            'expiration_year': 2020,
            'address_1': '123 Main Street',
            'address_2': 'Box 2',
            'state': 'Confusion',
            'zip': '90210'
        }
        card = billing.StripeCard('deadbeef')
        actual = dict([(name, card[name]) for name in expected])
        assert_equals(actual, expected)

    @mock.patch('stripe.Customer')
    def test_stripe_card_gives_empty_string_instead_of_KeyError(self, sc):
        stripe_customer = sc.retrieve.return_value
        stripe_customer.id = 'deadbeef'
        stripe_customer.get = {'active_card': {}}.get

        expected = ''
        actual = billing.StripeCard('deadbeef')['nothing']
        assert_equals(actual, expected)


class TestBalancedBankAccount(Harness):
    balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
    balanced_bank_account_uri = balanced_account_uri + '/bank_accounts/B123'

    @mock.patch('gittip.billing.balanced.Account')
    @mock.patch('gittip.billing.balanced.BankAccount')
    def test_balanced_bank_account(self, b_b_account, b_account):
        # b_account = balanced.Account
        # b_b_account = balanced.BankAccount
        # b_b_b_account = billing.BalancedBankAccount
        # got it?
        bank_account = mock.Mock()
        bank_account.is_valid = True
        b_account.find.return_value\
                 .bank_accounts.all.return_value = [bank_account]

        b_b_b_account = billing.BalancedBankAccount(self.balanced_account_uri)
        assert b_account.find.called_with(self.balanced_account_uri)
        assert b_b_account.find.called_with(self.balanced_bank_account_uri)

        assert b_b_b_account.is_setup
        with assert_raises(IndexError):
            b_b_b_account.__getitem__('invalid')

    def test_balanced_bank_account_not_setup(self):
        bank_account = billing.BalancedBankAccount(None)
        assert not bank_account.is_setup
        assert not bank_account['id']


class TestBillingAssociate(TestBillingBase):
    @mock.patch('gittip.billing.get_balanced_account')
    def test_associate_valid_card(self, gba):
        gba.return_value.uri = self.balanced_account_uri

        # first time through, payment processor account is None
        billing.associate(u"credit card", 'alice', None, self.card_uri)

        assert gba.call_count == 1
        assert gba.return_value.add_card.call_count == 1
        assert gba.return_value.add_bank_account.call_count == 0

    @mock.patch('balanced.Account.find')
    def test_associate_invalid_card(self, find):
        error_message = 'Something terrible'
        not_found = balanced.exc.HTTPError(error_message)
        find.return_value.add_card.side_effect = not_found

        # second time through, payment processor account is balanced
        # account_uri
        billing.associate(u"credit card", 'alice', self.balanced_account_uri,
                          self.card_uri)
        user = authentication.User.from_id('alice')
        # participant in db should be updated to reflect the error message of
        # last update
        assert user.last_bill_result == error_message
        assert find.call_count

    @mock.patch('gittip.billing.balanced.Account.find')
    def test_associate_bank_account_valid(self, find):

        billing.associate(u"bank account", 'alice', self.balanced_account_uri,
                          self.balanced_destination_uri)

        args, _ = find.call_args
        assert args == (self.balanced_account_uri,)

        args, _ = find.return_value.add_bank_account.call_args
        assert args == (self.balanced_destination_uri,)

        user = authentication.User.from_id('alice')

        # participant in db should be updated
        assert user.last_ach_result == ''

    @mock.patch('gittip.billing.balanced.Account.find')
    def test_associate_bank_account_invalid(self, find):
        ex = balanced.exc.HTTPError('errrrrror')
        find.return_value.add_bank_account.side_effect = ex
        billing.associate(u"bank account", 'alice', self.balanced_account_uri,
                          self.balanced_destination_uri)

        user = authentication.User.from_id('alice')

        # participant in db should be updated
        assert user.last_ach_result == 'errrrrror'


class TestBillingClear(TestBillingBase):
    @mock.patch('balanced.Account.find')
    def test_clear(self, find):
        valid_card = mock.Mock()
        valid_card.is_valid = True
        invalid_card = mock.Mock()
        invalid_card.is_valid = False
        card_collection = [valid_card, invalid_card]
        find.return_value.cards = card_collection

        MURKY = """\

            UPDATE participants
               SET balanced_account_uri='not null'
                 , last_bill_result='ooga booga'
             WHERE id=%s

        """
        gittip.db.execute(MURKY, ('alice',))

        billing.clear(u"credit card", 'alice', self.balanced_account_uri)

        assert not valid_card.is_valid
        assert valid_card.save.call_count
        assert not invalid_card.save.call_count

        user = authentication.User.from_id('alice')
        assert not user.last_bill_result
        assert user.balanced_account_uri

    @mock.patch('gittip.billing.balanced.Account')
    def test_clear_bank_account(self, b_account):
        valid_ba = mock.Mock()
        valid_ba.is_valid = True
        invalid_ba = mock.Mock()
        invalid_ba.is_valid = False
        ba_collection = [
            valid_ba, invalid_ba
        ]
        b_account.find.return_value.bank_accounts = ba_collection

        MURKY = """\

            UPDATE participants
               SET balanced_account_uri='not null'
                 , last_ach_result='ooga booga'
             WHERE id=%s

        """
        gittip.db.execute(MURKY, ('alice',))

        billing.clear(u"bank account", 'alice', 'something')

        assert not valid_ba.is_valid
        assert valid_ba.save.call_count
        assert not invalid_ba.save.call_count

        user = authentication.User.from_id('alice')
        assert not user.last_ach_result
        assert user.balanced_account_uri


class TestBillingStoreError(TestBillingBase):
    def test_store_error_stores_bill_error(self):
        billing.store_error(u"credit card", "alice", "cheese is yummy")
        rec = gittip.db.fetchone("select * from participants where id='alice'")
        expected = "cheese is yummy"
        actual = rec['last_bill_result']
        assert actual == expected, actual

    def test_store_error_stores_ach_error(self):
        for message in ['cheese is yummy', 'cheese smells like my vibrams']:
            billing.store_error(u"bank account", 'alice', message)
            rec = gittip.db.fetchone("select * from participants "
                                     "where id='alice'")
            assert rec['last_ach_result'] == message


# class TestBillingTransfer(testing.GittipPaydayTest):
#     def setUp(self):
#         super(TestBillingTransfer, self).setUp()
#         self.participant_id = 'lgtest'
#         self.balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
#         billing.db = self.db
#         # TODO: remove once we rollback transactions....
#         insert = '''
#             insert into paydays (
#                 ncc_failing, ts_end
#             )
#             select 0, '1970-01-01T00:00:00+00'::timestamptz
#             where not exists (
#                 select *
#                 from paydays
#                 where ts_end='1970-01-01T00:00:00+00'::timestamptz
#             )
#         '''
#         self.db.execute(insert)

#     def _get_payday(self, cursor):
#         SELECT_PAYDAY = '''
#             select *
#             from paydays
#             where ts_end='1970-01-01T00:00:00+00'::timestamptz
#         '''
#         cursor.execute(SELECT_PAYDAY)
#         return cursor.fetchone()

#     def _create_participant(self, name):
#         INSERT_PARTICIPANT = '''
#             insert into participants (
#                 id, pending, balance
#             ) values (
#                 %s, 0, 1
#             )
#         '''
#         return self.db.execute(INSERT_PARTICIPANT, (name,))

#     def test_transfer(self):
#         amount = Decimal('1.00')
#         sender = 'test_transfer_sender'
#         recipient = 'test_transfer_recipient'
#         self._create_participant(sender)
#         self._create_participant(recipient)

#         result = self.payday.transfer(sender, recipient, amount)
#         self.assertTrue(result)

#         # no balance remaining for a second transfer
#         result = self.payday.transfer(sender, recipient, amount)
#         self.assertFalse(result)

#     def test_debit_participant(self):
#         amount = Decimal('1.00')
#         participant = 'test_debit_participant'

#         def get_balance_amount(participant):
#             recipient_sql = '''
#             select balance
#             from participants
#             where id = %s
#             '''
#             return self.db.fetchone(recipient_sql, (participant,))['balance']

#         self._create_participant(participant)
#         initial_amount = get_balance_amount(participant)

#         with self.db.get_connection() as connection:
#             cursor = connection.cursor()

#             self.payday.debit_participant(cursor, participant, amount)
#             connection.commit()

#         final_amount = get_balance_amount(participant)
#         self.assertEqual(initial_amount - amount, final_amount)

#         # this will fail because not enough balance
#         with self.db.get_connection() as conn:
#             cur = conn.cursor()

#             with self.assertRaises(IntegrityError):
#                 self.payday.debit_participant(cur, participant, amount)

#     def test_credit_participant(self):
#         amount = Decimal('1.00')
#         recipient = 'test_credit_participant'

#         def get_pending_amount(recipient):
#             recipient_sql = '''
#             select pending
#             from participants
#             where id = %s
#             '''
#             return self.db.fetchone(recipient_sql, (recipient,))['pending']

#         self._create_participant(recipient)
#         initial_amount = get_pending_amount(recipient)

#         with self.db.get_connection() as conn:
#             cur = conn.cursor()

#             self.payday.credit_participant(cur, recipient, amount)
#             conn.commit()

#         final_amount = get_pending_amount(recipient)
#         self.assertEqual(initial_amount + amount, final_amount)

#     def test_record_transfer(self):
#         amount = Decimal('1.00')

#         # check with db that amount is what we expect
#         def assert_transfer(recipient, amount):
#             transfer_sql = '''
#                 select sum(amount) as sum
#                 from transfers
#                 where tippee = %s
#             '''
#             result = self.db.fetchone(transfer_sql, (recipient,))
#             self.assertEqual(result['sum'], amount)

#         recipients = [
#             'jim', 'jim', 'kate', 'bob',
#         ]
#         seen = []

#         for recipient in recipients:
#             if not recipient in seen:
#                 self._create_participant(recipient)
#                 seen.append(recipient)

#         with self.db.get_connection() as conn:
#             cur = conn.cursor()

#             for recipient in recipients:
#                 self.payday.record_transfer( cur
#                                            , self.participant_id
#                                            , recipient
#                                            , amount
#                                             )

#             conn.commit()

#         assert_transfer('jim', amount * 2)
#         assert_transfer('kate', amount)
#         assert_transfer('bob', amount)

#     def test_record_transfer_invalid_participant(self):
#         amount = Decimal('1.00')

#         with self.db.get_connection() as conn:
#             cur = conn.cursor()
#             with self.assertRaises(IntegrityError):
#                 self.payday.record_transfer(cur, 'idontexist', 'nori', amount)

#     def test_mark_transfer(self):
#         amount = Decimal('1.00')

#         with self.db.get_connection() as conn:
#             cur = conn.cursor()
#             payday = self._get_payday(cur)
#             self.payday.mark_transfer(cur, amount)
#             payday2 = self._get_payday(cur)

#         self.assertEqual(payday['ntransfers'] + 1,
#                          payday2['ntransfers'])
#         self.assertEqual(payday['transfer_volume'] + amount,
#                          payday2['transfer_volume'])



#class TestBillingPayouts(testing.GittipSettlementTest):
#    def setUp(self):
#        super(TestBillingPayouts, self).setUp()
#
#        # let's create a couple of exchanges + participants so we can simulate
#        # real life.
#        participants = [
#            ('claimed_recipient_without_balanced', None, None),
#            ('claimed_recipient_no_merchant', 'no_merchant', None),
#            ('claimed_recipient_no_bank_ac', 'merchant', None),
#            ('claimed_recipient_with_bank_ac', 'merchant', '/v1/bank_ac'),
#        ]
#
#        for participant in participants:
#            self._create_participant(*participant)
#            for i in range(1, 3):
#                self._create_exchange(participant[0], 3 * i, 0.5 * i)
#
#    def _create_participant(self,
#                            name,
#                            account_uri=None,
#                            destination_uri=None):
#        INSERT_PARTICIPANT = '''
#            insert into participants (
#                id, pending, balance, balanced_account_uri,
#                balanced_destination_uri
#            ) values (
#                %s, 0, 1, %s, %s
#            )
#        '''
#        return self.db.execute(INSERT_PARTICIPANT,
#                               (name, account_uri, destination_uri))
#
#    def _create_exchange(self, particpant_id, amount, fee):
#        return self.db.execute("""
#            INSERT INTO exchanges (participant_id, amount, fee) VALUES (
#                %s, %s, %s
#            )
#        """, (particpant_id, amount, fee))
#
#    @mock.patch('gittip.billing.payday.balanced.Account')
#    @mock.patch('gittip.billing.payday.balanced.Credit')
#    def test_it_all(self, b_credit, b_account):
#        """
#        This runs the whole thing from end to end with minimal mocking.
#        """
#        accounts = []
#
#        def find_account(account_uri):
#            account = mock.Mock()
#            accounts.append(account)
#            if account_uri != 'merchant':
#                account.roles = []
#            else:
#                account.roles = ['merchant']
#            account.credit.return_value.created_at = datetime.utcnow()
#            return account
#
#        b_credit.query.filter.side_effect = balanced.exc.NoResultFound
#        b_account.find = find_account
#
#        self.settlement_manager.run()
#
#        # two participants were merchants
#        self.assertEqual(sum(a.credit.call_count for a in accounts), 2)
#
#        self.settlement_manager.run()
#
#        # second time we run should create no new calls to credit as we have
#        # already market the exchanges as settled
#        self.assertEqual(sum(a.credit.call_count for a in accounts), 2)
#
#        recipients_who_should_be_settled = [
#            'claimed_recipient_no_bank_ac', 'claimed_recipient_with_bank_ac'
#        ]
#
#        settled_recipients = list(self.db.fetchall('''
#            SELECT participant_id, amount_in_cents
#            FROM settlements
#            WHERE settled IS NOT NULL
#        '''))
#
#        self.assertEqual(len(settled_recipients), 2)
#        for participant in settled_recipients:
#            self.assertIn(participant['participant_id'],
#                          recipients_who_should_be_settled)
#            self.assertEqual(participant['amount_in_cents'], 750)
#
#    @mock.patch('gittip.billing.payday.balanced.Account')
#    @mock.patch('gittip.billing.payday.balanced.Credit')
#    def test_credit_settlement(self, b_credit, b_account):
#        credit = mock.Mock()
#        credit.created_at = datetime.utcnow()
#        b_credit.query.filter.return_value.one.return_value = credit
#
#        settlement_id = 999
#        amount_in_cents = 500
#        balanced_account_uri = '/v1/accounts/X'
#        balanced_destination_uri = '/v1/bank_accounts/X'
#        self.settlement_manager.cur = cursor = mock.Mock()
#        account = mock.Mock()
#        b_account.find.return_value = account
#
#        cursor.rowcount = 2  # invalid
#
#        args = (settlement_id,
#                amount_in_cents,
#                balanced_account_uri,
#                balanced_destination_uri)
#
#        with self.assertRaises(AssertionError):
#            self.settlement_manager.credit_settlement(*args)
#
#        cursor.rowcount = 1
#
#        # should work fine, existing credit is returned and we mark as settled
#        self.settlement_manager.credit_settlement(*args)
#
#        _, kwargs = b_credit.query.filter.call_args
#        self.assertEqual(kwargs, {'settlement_id': settlement_id})
#
#        cursor_args, _ = cursor.execute.call_args
#        self.assertEqual(cursor_args[1], (credit.created_at, settlement_id))
#
#        # oh no, we will return
#        b_credit.query.filter.side_effect = balanced.exc.NoResultFound()
#
#        self.settlement_manager.credit_settlement(*args)
#
#        credit_args, credit_kwargs = account.credit.call_args
#        self.assertEqual(credit_args, (amount_in_cents,))
#        self.assertItemsEqual(credit_kwargs, dict(
#            destination_uri=balanced_destination_uri,
#            meta_data={'settlement_id': settlement_id},
#            description=u'Settlement {}'.format(settlement_id))
#        )
#
#    @mock.patch('gittip.billing.payday.balanced.Account')
#    @mock.patch('gittip.billing.payday.SettleExchanges.'
#                'get_exchanges_for_participant')
#    @mock.patch('gittip.billing.payday.SettleExchanges.'
#                'ask_participant_for_merchant_info')
#    def test_create_settlement_for_exchanges(self,
#                                             info_request,
#                                             get_exchanges,
#                                             b_account):
#
#        get_exchanges.return_value = []
#        account = mock.Mock()
#        account.roles = ['merchant']
#        account.bank_accounts.query.total = 0
#        b_account.find.return_value = None
#        participant_id = 'mjallday'
#        balanced_account_uri = '/v1/accounts/X'
#        self.settlement_manager.cur = cursor = mock.Mock()
#
#        # no account found
#        self.settlement_manager.create_settlement_for_exchanges(
#            participant_id, balanced_account_uri)
#
#        b_account.find.return_value = account
#
#        # no bank accounts
#        self.settlement_manager.create_settlement_for_exchanges(
#            participant_id, balanced_account_uri)
#
#        account.bank_accounts.query.total = 1
#        account.roles.pop()
#
#        # not a merchant
#        self.settlement_manager.create_settlement_for_exchanges(
#            participant_id, balanced_account_uri)
#
#        account.roles = ['merchant']
#
#        # everything passes
#        self.settlement_manager.create_settlement_for_exchanges(
#            participant_id, balanced_account_uri)
#
#        self.assertEqual(info_request.call_count, 3)
#        self.assertEqual(get_exchanges.call_count, 1)
#        self.assertEqual(cursor.call_count, 0)
#
#        exchanges = [
#            {'exchange_id': 1, 'amount': Decimal('1.23'),
#             'fee': Decimal('0.01')},
#            {'exchange_id': 2, 'amount': Decimal('1.23'),
#             'fee': Decimal('0.01')},
#            {'exchange_id': 3, 'amount': Decimal('1.23'),
#             'fee': Decimal('0.01')},
#        ]
#
#        get_exchanges.return_value = exchanges
#
#        self.settlement_manager.create_settlement_for_exchanges(
#            participant_id, balanced_account_uri)
#
#        # amount was too low to trigger a settlement
#        self.assertEqual(cursor.execute.call_count, 0)
#
#        exchanges.append({
#            'exchange_id': 4,
#            'amount': Decimal('10.23'),
#            'fee': Decimal('0.01')},
#        )
#
#        # setup db emulation
#        cursor.fetchone.return_value = {'id': 1}
#        cursor.rowcount = 3
#
#        with self.assertRaises(AssertionError):
#            self.settlement_manager.create_settlement_for_exchanges(
#                participant_id, balanced_account_uri)
#
#        self.assertEqual(cursor.execute.call_count, 2)
#
#        cursor.reset_mock()
#        cursor.rowcount = 4
#
#        # this one will work OK
#        self.settlement_manager.create_settlement_for_exchanges(
#            participant_id, balanced_account_uri)
#
#        self.assertEqual(cursor.execute.call_count, 2)
#
#        # let's check the parameters we passed to the DB
#        settlement_insert, _ = cursor.execute.call_args_list[0]
#        exchange_update, _ = cursor.execute.call_args_list[1]
#
#        _, args = settlement_insert
#        self.assertEqual(args, ('mjallday', 1388))
#
#        _, args = exchange_update
#        self.assertEqual(args, (1, (1, 2, 3, 4)))
