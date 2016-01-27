from __future__ import print_function, unicode_literals

from decimal import Decimal
import json

from liberapay.testing import Harness


class TestChartOfReceiving(Harness):

    def setUp(self):
        Harness.setUp(self)
        for participant in ['alice', 'bob']:
            p = self.make_participant(participant, balance=100)
            setattr(self, participant, p)

    def test_get_tip_distribution_handles_a_tip(self):
        self.alice.set_tip_to(self.bob, '3.00')
        expected = ([[Decimal('3.00'), 1, Decimal('3.00'), 1.0, Decimal('1')]],
                    1.0, Decimal('3.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_handles_no_tips(self):
        expected = ([], 0.0, Decimal('0.00'))
        actual = self.alice.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_handles_multiple_tips(self):
        carl = self.make_participant('carl', balance=100)
        self.alice.set_tip_to(self.bob, '1.00')
        carl.set_tip_to(self.bob, '3.00')
        expected = ([
            [Decimal('1.00'), 1, Decimal('1.00'), 0.5, Decimal('0.25')],
            [Decimal('3.00'), 1, Decimal('3.00'), 0.5, Decimal('0.75')]
        ], 2.0, Decimal('4.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_bad_cc(self):
        bad_cc = self.make_participant('bad_cc', last_bill_result='Failure!')
        self.alice.set_tip_to(self.bob, '1.00')
        bad_cc.set_tip_to(self.bob, '3.00')
        expected = ([[Decimal('1.00'), 1, Decimal('1.00'), 1, Decimal('1')]],
                    1.0, Decimal('1.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_missing_cc(self):
        missing_cc = self.make_participant('missing_cc')
        self.alice.set_tip_to(self.bob, '1.00')
        missing_cc.set_tip_to(self.bob, '3.00')
        expected = ([[Decimal('1.00'), 1, Decimal('1.00'), 1, Decimal('1')]],
                    1.0, Decimal('1.00'))
        actual = self.bob.get_tip_distribution()
        assert actual == expected

class TestJson(Harness):

    def test_200(self):
        response = self.client.GET('/about/stats.json')
        assert response.code == 200
        body = json.loads(response.body)
        assert len(body) > 0
