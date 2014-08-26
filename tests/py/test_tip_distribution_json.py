from __future__ import unicode_literals

import json
from decimal import Decimal as D

from gratipay.testing import Harness


class Tests(Harness):

    def test_tip_distribution_json_gives_tip_distribution(self):
        alice = self.make_participant('alice', claimed_time='now', last_bill_result='')
        bob = self.make_participant('bob', claimed_time='now', number='plural')
        carl = self.make_participant('carl', claimed_time='now', last_bill_result='')

        alice.set_tip_to(bob, '200.00')
        carl.set_tip_to(bob, '300.00')

        response = self.client.GET("/about/tip-distribution.json")
        tip_distribution = json.loads(response.body)
        assert tip_distribution == [D('200.0'), D('300.0')]
