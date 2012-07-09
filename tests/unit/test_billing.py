from __future__ import unicode_literals
import mock

import balanced

from gittip import billing

from tests import GittipBaseTest


class TestBilling(GittipBaseTest):
    def setUp(self):
        super(TestBilling, self).setUp()
        self.pp_customer_id = '/v1/marketplaces/M123/accounts/A123'

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
        customer = billing.Customer(self.pp_customer_id)
        self.assertEqual(customer['id'], balanced_account.uri)
        self.assertIn(card.last_four, customer['last4'])
        self.assertEqual(customer['expiry'], '10/2020')
        self.assertEqual(customer['nothing'], card.nothing)
