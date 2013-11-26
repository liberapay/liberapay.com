from __future__ import print_function, unicode_literals

import datetime
import json

from gittip.billing.payday import Payday
from gittip.testing import Harness
from gittip.testing.client import TestClient


class Tests(Harness):

    def make_participants_and_tips(self):
        alice = self.make_participant('alice', balance=10, claimed_time='now')
        bob = self.make_participant('bob', balance=10, claimed_time='now')
        self.make_participant('carl', claimed_time='now')

        alice.set_tip_to('carl', '1.00')
        bob.set_tip_to('carl', '2.00')

        return alice, bob

    def run_payday(self):
        Payday(self.db).run()


    def test_no_payday_returns_empty_list(self):
        self.make_participants_and_tips()
        assert json.loads(TestClient().get('/carl/charts.json').body) == []

    def test_one_payday_returns_empty_list(self):
        self.make_participants_and_tips()
        self.run_payday()
        assert json.loads(TestClient().get('/carl/charts.json').body) == []

    def test_second_payday_comes_through(self):
        alice, bob = self.make_participants_and_tips()

        # Suppress tips for the zeroth payday, because it's too hard to make
        # the two paydays run with different dates, and the charts.json queries
        # lump together based on payday date.
        alice.set_tip_to('carl', '0.00')
        bob.set_tip_to('carl', '0.00')
        self.run_payday()

        # Bring back tips for first payday.
        alice.set_tip_to('carl', '1.00')
        bob.set_tip_to('carl', '2.00')
        self.run_payday()

        expected = [ { "date": datetime.date.today().strftime('%Y-%m-%d')
                     , "npatrons": 2
                     , "receipts": 3.00
                      }
                    ]
        actual = json.loads(TestClient().get('/carl/charts.json').body)

        assert actual == expected
