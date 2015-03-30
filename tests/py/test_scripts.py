from __future__ import absolute_import, division, print_function, unicode_literals

import mock

from gratipay.testing import Harness
from gratipay.models.exchange_route import ExchangeRoute
from gratipay.models.participant import Participant
from tasks import set_paypal_email, bitcoin_payout


class TestScripts(Harness):
    def test_set_paypal_email(self):
        alice = self.make_participant('alice', api_key='abcdefgh')
        set_paypal_email(username='alice', email='alice@gmail.com', api_key_fragment=alice.api_key[0:8])
        route = ExchangeRoute.from_network(alice, 'paypal')
        assert route.address == 'alice@gmail.com'

    @mock.patch('tasks.coinbase_request')
    def test_bitcoin_payout(self, cb):
        # https://developers.coinbase.com/api#send-money
        cb.return_value.status_code = 200
        cb.return_value.json = lambda: {
            'success': True,
            'transfer': {
                'fees': {
                    'coinbase': {'currency_iso': 'USD', 'cents': 10},
                    'bank': {'currency_iso': 'USD', 'cents': 15}
                },
                'subtotal': {'currency': 'USD', 'amount': 20},
                'btc': {'currency': 'BTC', 'amount': 1}
            }
        }
        alice = self.make_participant('alice', api_key='abcdefgh', balance=100)
        route = ExchangeRoute.insert(alice, 'bitcoin', '17NdbrSGoUotzeGCcMMCqnFkEvLymoou9j')
        bitcoin_payout(username='alice', amount=20, api_key_fragment=alice.api_key[0:8])
        alice = Participant.from_username('alice')
        assert alice.balance == 79.75
        exchange = self.db.one("""
            SELECT *
              FROM exchanges
             WHERE participant='alice'
        """)
        assert exchange.amount == -20
        assert exchange.fee == 0.25
        assert exchange.route == route.id

