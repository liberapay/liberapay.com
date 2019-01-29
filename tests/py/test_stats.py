from decimal import Decimal
import json

from liberapay.models.exchange_route import ExchangeRoute
from liberapay.testing import EUR, Harness


class TestChartOfReceiving(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant('alice')
        self.alice_card = self.upsert_route(self.alice, 'stripe-card')
        self.bob = self.make_participant('bob')
        self.bob_stripe_account = self.add_payment_account(self.bob, 'stripe')

    def test_get_tip_distribution_handles_a_tip(self):
        self.alice.set_tip_to(self.bob, EUR('3.00'))
        self.make_payin_and_transfer(self.alice_card, self.bob, EUR('9.00'))
        expected = ([[EUR('3.00'), 1, EUR('3.00'), EUR('3.00'), 1.0, Decimal('1')]],
                    1, EUR('3.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_handles_no_tips(self):
        expected = ([], 0.0, EUR('0.00'))
        actual = self.alice.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_handles_multiple_tips(self):
        self.alice.set_tip_to(self.bob, EUR('1.00'))
        self.make_payin_and_transfer(self.alice_card, self.bob, EUR('8.00'))
        carl = self.make_participant('carl')
        carl_card = self.upsert_route(carl, 'stripe-card')
        carl.set_tip_to(self.bob, EUR('3.00'))
        self.make_payin_and_transfer(carl_card, self.bob, EUR('3.00'))
        expected = ([
            [EUR('1.00'), 1, EUR('1.00'), EUR('1.00'), 0.5, Decimal('0.25')],
            [EUR('3.00'), 1, EUR('3.00'), EUR('3.00'), 0.5, Decimal('0.75')]
        ], 2, EUR('4.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_bad_cc(self):
        bad_cc = self.make_participant('bad_cc')
        ExchangeRoute.insert(bad_cc, 'mango-cc', '-1', 'failed', currency='EUR')
        self.alice.set_tip_to(self.bob, EUR('1.00'))
        self.make_payin_and_transfer(self.alice_card, self.bob, EUR('25.00'))
        bad_cc.set_tip_to(self.bob, EUR('3.00'))
        expected = ([[EUR('1.00'), 1, EUR('1.00'), EUR('1.00'), 1, Decimal('1')]],
                    1, EUR('1.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_missing_cc(self):
        missing_cc = self.make_participant('missing_cc')
        self.alice.set_tip_to(self.bob, EUR('1.00'))
        self.make_payin_and_transfer(self.alice_card, self.bob, EUR('4.00'))
        missing_cc.set_tip_to(self.bob, EUR('3.00'))
        expected = ([[EUR('1.00'), 1, EUR('1.00'), EUR('1.00'), 1, Decimal('1')]],
                    1.0, EUR('1.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_old_or_nonfunded_tip(self):
        self.alice.set_tip_to(self.bob, EUR('3.00'))  # funded
        self.alice.set_tip_to(self.bob, EUR('100.00'))  # not funded
        expected = ([], 0, EUR('0.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

class TestJson(Harness):

    def test_200(self):
        response = self.client.GET('/about/stats.json')
        assert response.code == 200
        body = json.loads(response.text)
        assert len(body) > 0
