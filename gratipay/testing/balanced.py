from __future__ import absolute_import, division, print_function, unicode_literals

import itertools

import balanced

from gratipay.models.exchange_route import ExchangeRoute
from gratipay.testing import Harness
from gratipay.testing.vcr import use_cassette


class BalancedHarness(Harness):

    def setUp(self):
        self.david = self.make_participant('david', is_suspicious=False,
                                           claimed_time='now',
                                           balanced_customer_href=self.david_href)
        self.janet = self.make_participant('janet', is_suspicious=False,
                                           claimed_time='now',
                                           balanced_customer_href=self.janet_href)
        self.janet_route = ExchangeRoute.insert(self.janet, 'balanced-cc', self.card_href)
        self.homer = self.make_participant('homer', is_suspicious=False,
                                           claimed_time='now',
                                           balanced_customer_href=self.homer_href)
        self.homer_route = ExchangeRoute.insert(self.homer, 'balanced-ba', self.bank_account_href)

    @classmethod
    def tearDownClass(cls):
        has_exchange_id = balanced.Transaction.f.meta.contains('exchange_id')
        credits = balanced.Credit.query.filter(has_exchange_id)
        debits = balanced.Debit.query.filter(has_exchange_id)
        for t in itertools.chain(credits, debits):
            t.meta.pop('exchange_id')
            t.save()
        super(BalancedHarness, cls).tearDownClass()


with use_cassette('BalancedHarness'):
    cls = BalancedHarness
    balanced.configure(balanced.APIKey().save().secret)
    mp = balanced.Marketplace.my_marketplace
    if not mp:
        mp = balanced.Marketplace().save()
    cls.balanced_marketplace = mp

    cls.david_href = cls.make_balanced_customer()

    cls.janet_href = cls.make_balanced_customer()
    cls.card = balanced.Card(
        number='4111111111111111',
        expiration_month=10,
        expiration_year=2020,
        address={
            'line1': "123 Main Street",
            'state': 'Confusion',
            'postal_code': '90210',
        },
        # gratipay stores some of the address data in the meta fields,
        # continue using them to support backwards compatibility
        meta={
            'address_2': 'Box 2',
            'city_town': '',
            'region': 'Confusion',
        }
    ).save()
    cls.card.associate_to_customer(cls.janet_href)
    cls.card_href = unicode(cls.card.href)

    cls.homer_href = cls.make_balanced_customer()
    cls.bank_account = balanced.BankAccount(
        name='Homer Jay',
        account_number='112233a',
        routing_number='121042882',
    ).save()
    cls.bank_account.associate_to_customer(cls.homer_href)
    cls.bank_account_href = unicode(cls.bank_account.href)
