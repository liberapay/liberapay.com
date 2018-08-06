from __future__ import print_function, unicode_literals

from decimal import Decimal
import json

from liberapay.testing import EUR, Harness


class TestChartOfReceiving(Harness):

    def setUp(self):
        Harness.setUp(self)
        for participant in ['alice', 'bob']:
            p = self.make_participant(participant, balance=EUR(10))
            setattr(self, participant, p)

    def test_get_tip_distribution_handles_a_tip(self):
        self.alice.set_tip_to(self.bob, EUR('3.00'))
        expected = ([[EUR('3.00'), 1, EUR('3.00'), EUR('3.00'), 1.0, Decimal('1')]],
                    1, EUR('3.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_handles_no_tips(self):
        expected = ([], 0.0, EUR('0.00'))
        actual = self.alice.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_handles_multiple_tips(self):
        carl = self.make_participant('carl', balance=EUR(100))
        self.alice.set_tip_to(self.bob, EUR('1.00'))
        carl.set_tip_to(self.bob, EUR('3.00'))
        expected = ([
            [EUR('1.00'), 1, EUR('1.00'), EUR('1.00'), 0.5, Decimal('0.25')],
            [EUR('3.00'), 1, EUR('3.00'), EUR('3.00'), 0.5, Decimal('0.75')]
        ], 2, EUR('4.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_bad_cc(self):
        bad_cc = self.make_participant('bad_cc', route_status='failed')
        self.alice.set_tip_to(self.bob, EUR('1.00'))
        bad_cc.set_tip_to(self.bob, EUR('3.00'))
        expected = ([[EUR('1.00'), 1, EUR('1.00'), EUR('1.00'), 1, Decimal('1')]],
                    1, EUR('1.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_missing_cc(self):
        missing_cc = self.make_participant('missing_cc')
        self.alice.set_tip_to(self.bob, EUR('1.00'))
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
