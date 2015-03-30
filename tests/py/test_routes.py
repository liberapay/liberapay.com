from __future__ import absolute_import, division, print_function, unicode_literals

import balanced
import mock

from gratipay.testing.balanced import BalancedHarness
from gratipay.models.exchange_route import ExchangeRoute
from gratipay.models.participant import Participant


class TestRoutes(BalancedHarness):

    def hit(self, username, action, network, address, expected=200):
        r =  self.client.POST('/%s/routes/%s.json' % (username, action),
                              data=dict(network=network, address=address),
                              auth_as=username, raise_immediately=False)
        assert r.code == expected
        return r

    def test_associate_and_delete_valid_card(self):
        card = balanced.Card(
            number='4242424242424242',
            expiration_year=2020,
            expiration_month=12
        ).save()
        customer = self.david.get_balanced_account()
        self.hit('david', 'associate', 'balanced-cc', card.href)

        cards = customer.cards.all()
        assert len(cards) == 1
        assert cards[0].href == card.href

        assert self.david.get_credit_card_error() == ''

        self.hit('david', 'delete', 'balanced-cc', card.href)

        david = Participant.from_username('david')
        assert david.get_credit_card_error() == 'invalidated'
        assert david.balanced_customer_href

    def test_associate_invalid_card(self):
        self.hit('david', 'associate', 'balanced-cc', '/cards/CC123123123123', expected=400)
        assert self.david.get_credit_card_error() is None

    def test_associate_and_delete_bank_account_valid(self):
        bank_account = balanced.BankAccount( name='Alice G. Krebs'
                                           , routing_number='321174851'
                                           , account_number='9900000001'
                                           , account_type='checking'
                                            ).save()
        customer = self.david.get_balanced_account()
        customer.merchant_status = 'underwritten'
        with mock.patch.object(Participant, 'get_balanced_account') as gba:
            gba.return_value = customer
            self.hit('david', 'associate', 'balanced-ba', bank_account.href)

        bank_accounts = customer.bank_accounts.all()
        assert len(bank_accounts) == 1
        assert bank_accounts[0].href == bank_account.href

        assert self.david.get_bank_account_error() == ''

        self.hit('david', 'delete', 'balanced-ba', bank_account.href)

        david = Participant.from_username('david')
        assert david.get_bank_account_error() == 'invalidated'
        assert david.balanced_customer_href

    @mock.patch.object(Participant, 'get_balanced_account')
    def test_associate_bank_account_invalid(self, gba):
        gba.return_value.merchant_status = 'underwritten'
        self.hit('david', 'associate', 'balanced-ba', '/bank_accounts/BA123123123', expected=400)
        assert self.david.get_bank_account_error() is None

    def test_associate_bitcoin(self):
        addr = '17NdbrSGoUotzeGCcMMCqnFkEvLymoou9j'
        self.hit('david', 'associate', 'bitcoin', addr)
        route = ExchangeRoute.from_network(self.david, 'bitcoin')
        assert route.address == addr
        assert route.error == ''

    def test_associate_bitcoin_invalid(self):
        self.hit('david', 'associate', 'bitcoin', '12345', expected=400)
        assert not ExchangeRoute.from_network(self.david, 'bitcoin')

    def test_bank_account(self):
        expected = "add or change your bank account"
        actual = self.client.GET('/alice/routes/bank-account.html').body
        assert expected in actual

    def test_bank_account_auth(self):
        self.make_participant('alice', claimed_time='now')
        expected = '<em id="status">not connected</em>'
        actual = self.client.GET('/alice/routes/bank-account.html', auth_as='alice').body
        assert expected in actual

    def test_credit_card(self):
        self.make_participant('alice', claimed_time='now')
        expected = "add or change your credit card"
        actual = self.client.GET('/alice/routes/credit-card.html').body
        assert expected in actual

    def test_credit_card_page_shows_card_missing(self):
        self.make_participant('alice', claimed_time='now')
        expected = 'Your credit card is <em id="status">missing'
        actual = self.client.GET('/alice/routes/credit-card.html', auth_as='alice').body.decode('utf8')
        assert expected in actual

    def test_credit_card_page_loads_when_there_is_a_card(self):
        expected = 'Your credit card is <em id="status">working'
        actual = self.client.GET('/janet/routes/credit-card.html', auth_as='janet').body.decode('utf8')
        assert expected in actual

    def test_credit_card_page_shows_card_failing(self):
        ExchangeRoute.from_network(self.janet, 'balanced-cc').update_error('Some error')
        expected = 'Your credit card is <em id="status">failing'
        actual = self.client.GET('/janet/routes/credit-card.html', auth_as='janet').body.decode('utf8')
        assert expected in actual

    def test_receipt_page_loads(self):
        ex_id = self.make_exchange('balanced-cc', 113, 30, self.janet)
        url_receipt = '/janet/receipts/{}.html'.format(ex_id)
        actual = self.client.GET(url_receipt, auth_as='janet').body.decode('utf8')
        assert 'Visa' in actual
