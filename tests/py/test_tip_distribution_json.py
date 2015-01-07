from __future__ import unicode_literals

import json

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
        assert tip_distribution == [
            {'lo': '0.00', 'hi': '0.10', 'sum': '0', 'ntips': '0', 'xText': '0.10'},
            {'lo': '0.11', 'hi': '0.20', 'sum': '0', 'ntips': '0', 'xText': '0.20'},
            {'lo': '0.21', 'hi': '0.50', 'sum': '0', 'ntips': '0', 'xText': '0.50'},

            {'lo': '0.51', 'hi': '1.00', 'sum': '0', 'ntips': '0', 'xText': '1.00'},
            {'lo': '1.01', 'hi': '2.00', 'sum': '0', 'ntips': '0', 'xText': '2.00'},
            {'lo': '2.01', 'hi': '5.00', 'sum': '0', 'ntips': '0', 'xText': '5.00'},

            {'lo': '5.01', 'hi': '10.00', 'sum': '0', 'ntips': '0', 'xText': '10.00'},
            {'lo': '10.01', 'hi': '20.00', 'sum': '0', 'ntips': '0', 'xText': '20.00'},
            {'lo': '20.01', 'hi': '50.00', 'sum': '0', 'ntips': '0', 'xText': '50.00'},

            {'lo': '50.01', 'hi': '100.00', 'sum': '0', 'ntips': '0', 'xText': '100.00'},
            {'lo': '100.01', 'hi': '200.00', 'sum': '200.00', 'ntips': '1', 'xText': '200.00'},
            {'lo': '200.01', 'hi': '500.00', 'sum': '300.00', 'ntips': '1', 'xText': '500.00'},

            {'lo': '500.01', 'hi': '1000.00', 'sum': '0', 'ntips': '0', 'xText': '1000.00'},
        ]
