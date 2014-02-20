from __future__ import absolute_import, division, print_function, unicode_literals

import balanced

from gittip.testing import Harness


class BalancedHarness(Harness):

    @classmethod
    def setUpClass(cls):
        super(BalancedHarness, cls).setUpClass()
        cls.balanced_api_key = balanced.APIKey().save().secret
        balanced.configure(cls.balanced_api_key)
        mp = balanced.Marketplace.my_marketplace
        if not mp:
            mp = balanced.Marketplace().save()
        cls.balanced_marketplace = mp


    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant('alice', elsewhere='github')

        self.balanced_customer_href = unicode(balanced.Customer().save().href)
        self.card_href = unicode(balanced.Card(
            number='4111111111111111',
            expiration_month=10,
            expiration_year=2020,
            address={
                'line1': "123 Main Street",
                'state': 'Confusion',
                'postal_code': '90210',
            },
            # gittip stores some of the address data in the meta fields,
            # continue using them to support backwards compatibility
            meta={
                'address_2': 'Box 2',
                'city_town': '',
                'region': 'Confusion',
            }
        ).save().href) # XXX Why don't we actually associate this with the customer? See XXX in
                       # test_billing_payday.TestPaydayChargeOnBalanced.
        self.bank_account_href = unicode(balanced.BankAccount(
            name='Homer Jay',
            account_number='112233a',
            routing_number='121042882',
        ).save().href)
