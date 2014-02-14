from __future__ import unicode_literals

import balanced
import mock

from gittip import billing
from gittip.security import authentication
from gittip.testing import Harness
from gittip.models.participant import Participant


def setUp_balanced(o):
    o.balanced_api_key = balanced.APIKey().save().secret
    balanced.configure(o.balanced_api_key)
    mp = balanced.Marketplace.my_marketplace
    if not mp:
        mp = balanced.Marketplace().save()
    o.balanced_marketplace = mp


def setUp_balanced_resources(o):
    o.balanced_customer_href = balanced.Customer().save().href
    o.card_href = balanced.Card(
        number='4111111111111111',
        expiration_month=10,
        expiration_year=2020,
        address={
            'line1': "123 Main Street",
            'state': 'Confusion',
            'postal_code': '90210',
        },
        # the current gittip system stores some of the address data
        # in the meta fields, continue using them to support backwards
        # compatibility
        meta={
            'address_2': 'Box 2',
            'city_town': '',
            'region': 'Confusion',
        }
    ).save().href
    o.bank_account_href = balanced.BankAccount(
        name='Homer Jay',
        account_number='112233a',
        routing_number='121042882',
    ).save().href


class TestBillingBase(Harness):
    #balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
    #balanced_destination_uri = '/v1/bank_accounts/X'
    #card_uri = '/v1/marketplaces/M123/accounts/A123/cards/C123'

    @classmethod
    def setUpClass(cls):
        super(TestBillingBase, cls).setUpClass()
        setUp_balanced(cls)

    def setUp(self):
        Harness.setUp(self)
        setUp_balanced_resources(self)
        self.alice = self.make_participant('alice', elsewhere='github')


class TestBalancedCard(Harness):

    #balanced_customer_href = '/customers/CU123123'
    #balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'

    @classmethod
    def setUpClass(cls):
        super(TestBalancedCard, cls).setUpClass()
        setUp_balanced(cls)

    def setUp(self):
        Harness.setUp(self)
        setUp_balanced_resources(self)

    def test_balanced_card_basically_works(self):
        balanced.Card.fetch(self.card_href) \
                     .associate_to_customer(self.balanced_customer_href)
        # card = mock.Mock()
        # card.number = 'xxxxxxxxxxxx1234'
        # card.expiration_month = 10
        # card.expiration_year = 2020
        # card.street_address = "123 Main Street"
        # card.meta = {"address_2": "Box 2"}
        # card.region = "Confusion"
        # card.postal_code = "90210"

        # balanced_account = ba.find.return_value
        # balanced_account.uri = self.balanced_customer_href
        # balanced_account.cards = mock.Mock()
        # balanced_account.cards.all.return_value = [card]

        expected = {
            'id': self.balanced_customer_href,
            'last_four': 'xxxxxxxxxxxx1111',
            'last4': 'xxxxxxxxxxxx1111',
            'expiration_month': 10,
            'expiration_year': 2020,
            'address_1': '123 Main Street',
            'address_2': 'Box 2',
            'state': 'Confusion',
            'zip': '90210',
        }
        card = billing.BalancedCard(self.balanced_customer_href)
        actual = dict([(name, card[name]) for name in expected])
        assert actual == expected

    @mock.patch('balanced.Customer')
    def test_balanced_card_gives_class_name_instead_of_KeyError(self, ba):
        card = mock.Mock()

        balanced_account = ba.find.return_value
        balanced_account.href = self.balanced_customer_href
        balanced_account.cards = mock.Mock()
        balanced_account.cards.all.return_value = [card]

        card = billing.BalancedCard(self.balanced_customer_href)

        expected = mock.Mock.__name__
        actual = card['nothing'].__class__.__name__
        assert actual == expected


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
        assert actual == expected

    @mock.patch('stripe.Customer')
    def test_stripe_card_gives_empty_string_instead_of_KeyError(self, sc):
        stripe_customer = sc.retrieve.return_value
        stripe_customer.id = 'deadbeef'
        stripe_customer.get = {'active_card': {}}.get

        expected = ''
        actual = billing.StripeCard('deadbeef')['nothing']
        assert actual == expected


class TestBalancedBankAccount(Harness):
    #balanced_account_uri = '/v1/marketplaces/M123/accounts/A123'
    # balanced_bank_account_uri = balanced_account_uri + '/bank_accounts/B123'

    @classmethod
    def setUpClass(cls):
        super(TestBalancedBankAccount, cls).setUpClass()
        setUp_balanced(cls)

    def setUp(self):
        Harness.setUp(self)
        setUp_balanced_resources(self)

    #@mock.patch('gittip.billing.balanced.Customer')
    #@mock.patch('gittip.billing.balanced.BankAccount')
    def test_balanced_bank_account(self): #, b_b_account, b_account):
        balanced.BankAccount.fetch(self.bank_account_href).associate_to_customer(self.balanced_customer_href)
        # b_account = balanced.Customer
        # b_b_account = balanced.BankAccount
        # b_b_b_account = billing.BalancedBankAccount
        # got it?
        #bank_account = mock.Mock()
        #bank_account.is_valid = True

        #b_account.find.return_value\
        #         .bank_accounts.all.return_value = [bank_account]

        ba_account = billing.BalancedBankAccount(self.balanced_customer_href)

        assert ba_account.is_setup

        # b_b_b_account = billing.BalancedBankAccount(self.balanced_account_uri)

        # assert b_account.find.called_with(self.balanced_account_uri)
        # assert b_b_account.find.called_with(self.balanced_bank_account_uri)

        # assert b_b_b_account.is_setup
        with self.assertRaises(IndexError):
            ba_account.__getitem__('invalid')

    #@mock.patch('gittip.billing.balanced.Customer')
    #@mock.patch('gittip.billing.balanced.BankAccount')
    def test_balanced_bank_account_account_uri(self) :#, b_b_account, b_account):
        # b_account = balanced.Account
        # b_b_account = balanced.BankAccount
        # b_b_b_account = billing.BalancedBankAccount
        # got it?
        bank_account = mock.Mock()
        bank_account.is_valid = True
        b_account.find.return_value\
                 .bank_accounts.all.return_value = [bank_account]
        b_account.uri = "Here I am!"
        bank_account.account = b_account

        b_b_b_account = billing.BalancedBankAccount(self.balanced_customer_href)

        expected = "Here I am!"
        actual = b_b_b_account['account_uri']
        assert actual == expected

    def test_balanced_bank_account_not_setup(self):
        bank_account = billing.BalancedBankAccount(None)
        assert not bank_account.is_setup
        assert not bank_account['id']


class TestBillingAssociate(TestBillingBase):
    @mock.patch('gittip.billing.balanced.Customer.fetch')
    @mock.patch('gittip.billing.get_balanced_account')
    def test_associate_valid_card(self, gba, find):
        find.return_value.uri = self.balanced_account_uri
        gba.return_value.uri = self.balanced_account_uri

        # first time through, payment processor account is None
        billing.associate(self.db, u"credit card", 'alice', None, self.card_uri)

        assert gba.call_count == 1
        assert gba.return_value.add_card.call_count == 1
        assert gba.return_value.add_bank_account.call_count == 0

    @mock.patch('balanced.Customer.fetch')
    def test_associate_invalid_card(self, find):
        error_message = 'Something terrible'
        not_found = balanced.exc.HTTPError(error_message)
        find.return_value.add_card.side_effect = not_found
        find.return_value.uri = self.balanced_account_uri

        # second time through, payment processor account is balanced
        # account_uri
        billing.associate( self.db
                         , u"credit card"
                         , 'alice'
                         , self.balanced_account_uri
                         , self.card_uri
                          )
        user = authentication.User.from_username('alice')
        # participant in db should be updated to reflect the error message of
        # last update
        assert user.participant.last_bill_result == error_message
        assert find.call_count

    @mock.patch('gittip.billing.balanced.Customer.find')
    def test_associate_bank_account_valid(self, find):

        find.return_value.uri = self.balanced_account_uri
        billing.associate( self.db
                         , u"bank account"
                         , 'alice'
                         , self.balanced_account_uri
                         , self.balanced_destination_uri
                          )

        args, _ = find.call_args
        assert args == (self.balanced_account_uri,)

        args, _ = find.return_value.add_bank_account.call_args
        assert args == (self.balanced_destination_uri,)

        user = authentication.User.from_username('alice')

        # participant in db should be updated
        assert user.participant.last_ach_result == ''

    @mock.patch('gittip.billing.balanced.Customer.find')
    def test_associate_bank_account_invalid(self, find):
        ex = balanced.exc.HTTPError('errrrrror')
        find.return_value.add_bank_account.side_effect = ex
        find.return_value.uri = self.balanced_account_uri

        billing.associate( self.db
                         , u"bank account"
                         , 'alice'
                         , self.balanced_account_uri
                         , self.balanced_destination_uri
                          )

        # participant in db should be updated
        alice = Participant.from_username('alice')
        assert alice.last_ach_result == 'errrrrror'


class TestBillingClear(TestBillingBase):

    @mock.patch('balanced.Customer.find')
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
             WHERE username=%s

        """
        self.db.run(MURKY, ('alice',))

        billing.clear(self.db, u"credit card", 'alice', self.balanced_account_uri)

        assert not valid_card.is_valid
        assert valid_card.save.call_count
        assert not invalid_card.save.call_count

        user = authentication.User.from_username('alice')
        assert not user.participant.last_bill_result
        assert user.participant.balanced_account_uri

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
             WHERE username=%s

        """
        self.db.run(MURKY, ('alice',))

        billing.clear(self.db, u"bank account", 'alice', 'something')

        assert not valid_ba.is_valid
        assert valid_ba.save.call_count
        assert not invalid_ba.save.call_count

        user = authentication.User.from_username('alice')
        assert not user.participant.last_ach_result
        assert user.participant.balanced_account_uri


class TestBillingStoreError(TestBillingBase):
    def test_store_error_stores_bill_error(self):
        billing.store_error(self.db, u"credit card", "alice", "cheese is yummy")
        rec = self.db.one("select * from participants where "
                            "username='alice'")
        expected = "cheese is yummy"
        actual = rec.last_bill_result
        assert actual == expected

    def test_store_error_stores_ach_error(self):
        for message in ['cheese is yummy', 'cheese smells like my vibrams']:
            billing.store_error(self.db, u"bank account", 'alice', message)
            rec = self.db.one("select * from participants "
                                "where username='alice'")
            assert rec.last_ach_result == message
