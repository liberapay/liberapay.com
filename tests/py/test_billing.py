from __future__ import absolute_import, division, print_function, unicode_literals

import balanced
import mock

from gittip import billing
from gittip.testing import Harness
from gittip.testing.balanced import BalancedHarness
from gittip.models.participant import Participant


class TestBalancedCard(BalancedHarness):

    def test_balanced_card_basically_works(self):
        expected = {
            'id': self.janet_href,
            'last_four': 'xxxxxxxxxxxx1111',
            'last4': 'xxxxxxxxxxxx1111',
            'expiration_month': 10,
            'expiration_year': 2020,
            'address_1': '123 Main Street',
            'address_2': 'Box 2',
            'state': 'Confusion',
            'zip': '90210',
        }
        card = billing.BalancedCard(self.janet_href)
        actual = dict([(name, card[name]) for name in expected])
        assert actual == expected

    def test_credit_card_page_shows_card_missing(self):
        self.make_participant('alice')
        expected = 'Your credit card is <em id="status">missing'
        actual = self.client.GET('/credit-card.html', auth_as='alice').body.decode('utf8')
        assert expected in actual

    def test_credit_card_page_loads_when_there_is_a_card(self):
        expected = 'Your credit card is <em id="status">working'
        actual = self.client.GET('/credit-card.html', auth_as='janet').body.decode('utf8')
        assert expected in actual

    def test_credit_card_page_loads_when_there_is_an_account_but_no_card(self):
        self.db.run( "UPDATE participants "
                     "SET last_bill_result='NoResultFound()'"
                     "WHERE username='janet'"
                    )

        expected = 'Your credit card is <em id="status">failing'
        actual = self.client.GET('/credit-card.html', auth_as='janet').body.decode('utf8')
        assert expected in actual

    @mock.patch('balanced.Customer')
    def test_balanced_card_gives_class_name_instead_of_KeyError(self, ba):
        card = mock.Mock()

        balanced_account = ba.fetch.return_value
        balanced_account.href = self.janet_href
        balanced_account.cards = mock.Mock()
        balanced_account.cards.filter.return_value.all.return_value = [card]

        card = billing.BalancedCard(self.janet_href)

        expected = mock.Mock.__name__
        actual = card['nothing'].__class__.__name__

        assert actual == expected

    def test_balanced_works_with_old_urls(self):
        # gittip will have a combination of old style from v1
        # and new urls from v1.1
        # do not actually do this in any real system
        # but construct the url using the id from the
        # customer and marketplace on the new api
        # to match the format of that of the old one
        url_user = '/v1/marketplaces/{}/accounts/{}'.format(
            self.balanced_marketplace.id,
            self.janet_href.split('/customers/')[1])

        card = billing.BalancedCard(url_user)

        assert card._thing.href == self.card_href


class TestBalancedBankAccount(BalancedHarness):

    def test_balanced_bank_account(self):
        ba_account = billing.BalancedBankAccount(self.homer_href)

        assert ba_account.is_setup

        with self.assertRaises(KeyError):
            ba_account.__getitem__('invalid')

        actual = ba_account['customer_href']
        expected = self.homer_href
        assert actual == expected

    def test_balanced_bank_account_not_setup(self):
        bank_account = billing.BalancedBankAccount(None)
        assert not bank_account.is_setup
        assert not bank_account['id']

    def test_balanced_bank_has_an_account_number(self):
        bank_account = billing.BalancedBankAccount(self.homer_href)
        assert bank_account['account_number'] == 'xxx233a'


class TestBillingAssociate(BalancedHarness):

    def test_associate_valid_card(self):
        self.david.set_tip_to(self.homer, 10)
        card = balanced.Card(
            number='4242424242424242',
            expiration_year=2020,
            expiration_month=12
        ).save()
        billing.associate( self.db
                         , 'credit card'
                         , 'david'
                         , self.david_href
                         , unicode(card.href)
                          )

        customer = balanced.Customer.fetch(self.david_href)
        cards = customer.cards.all()
        assert len(cards) == 1
        assert cards[0].href == card.href

        homer = Participant.from_id(self.homer.id)
        assert homer.receiving == 10

    def test_associate_invalid_card(self): #, find):
        billing.associate( self.db
                         , u"credit card"
                         , 'david'
                         , self.david_href
                         , '/cards/CC123123123123',  # invalid href
                          )
        david = Participant.from_username('david')
        assert david.last_bill_result == '404 Client Error: NOT FOUND'

    def test_associate_bank_account_valid(self):
        bank_account = balanced.BankAccount( name='Alice G. Krebs'
                                           , routing_number='321174851'
                                           , account_number='9900000001'
                                           , account_type='checking'
                                            ).save()
        billing.associate( self.db
                         , u"bank account"
                         , 'david'
                         , self.david_href
                         , unicode(bank_account.href)
                          )

        #args, _ = find.call_args

        customer = balanced.Customer.fetch(self.david_href)
        bank_accounts = customer.bank_accounts.all()
        assert len(bank_accounts) == 1
        assert bank_accounts[0].href == unicode(bank_account.href)

        david = Participant.from_username('david')
        assert david.last_ach_result == ''

    def test_associate_bank_account_invalid(self):

        billing.associate( self.db
                         , u"bank account"
                         , 'david'
                         , self.david_href
                         , '/bank_accounts/BA123123123123123123' # invalid href
                          )

        david = Participant.from_username('david')
        assert david.last_ach_result == '404 Client Error: NOT FOUND'


class TestBillingClear(BalancedHarness):

    def test_clear(self):
        billing.clear(self.db, u"credit card", 'david', self.david_href)

        customer = balanced.Customer.fetch(self.david_href)
        cards = customer.cards.all()
        assert len(cards) == 0

        david = Participant.from_username('david')
        assert david.last_bill_result is None
        assert david.balanced_customer_href

    def test_clear_bank_account(self):
        billing.clear(self.db, u"bank account", 'david', self.david_href)

        customer = balanced.Customer.fetch(self.david_href)
        bank_accounts = customer.bank_accounts.all()
        assert len(bank_accounts) == 0

        david = Participant.from_username('david')
        assert david.last_ach_result is None
        assert david.balanced_customer_href


class TestBillingStoreError(Harness):

    def setUp(self):
        super(TestBillingStoreError, self).setUp()
        self.make_participant('alice')

    def test_store_error_stores_bill_error(self):
        billing.store_error(self.db, u"credit card", "alice", "cheese is yummy")
        alice = Participant.from_username('alice')
        assert alice.last_bill_result == "cheese is yummy"

    def test_store_error_stores_ach_error(self):
        for message in ['cheese is yummy', 'cheese smells like my vibrams']:
            billing.store_error(self.db, u"bank account", 'alice', message)
            alice = Participant.from_username('alice')
            assert alice.last_ach_result == message
