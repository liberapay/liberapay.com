from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import json

from pando.utils import utcnow

from liberapay.billing.payday import Payday
from liberapay.testing.mangopay import FakeTransfersHarness


def today():
    return datetime.datetime.utcnow().date().strftime('%Y-%m-%d')


class TestChartsJson(FakeTransfersHarness):

    def setUp(self):
        super(TestChartsJson, self).setUp()

        self.alice = self.make_participant('alice')
        self.bob = self.make_participant('bob')
        self.carl = self.make_participant('carl')
        self.make_exchange('mango-cc', 10, 0, self.alice)
        self.make_exchange('mango-cc', 10, 0, self.bob)
        self.make_participant('notactive')

        self.alice.set_tip_to(self.carl, '1.00')
        self.bob.set_tip_to(self.carl, '2.00')

    def run_payday(self):
        Payday.start().run()


    def test_no_payday_returns_empty_list(self):
        assert json.loads(self.client.GET('/carl/charts.json').text) == []

    def test_first_payday_comes_through(self):
        self.run_payday()   # first

        expected = [{"date": today(), "npatrons": 2, "receipts": 3.00}]
        actual = json.loads(self.client.GET('/carl/charts.json').text)

        assert actual == expected

    def test_second_payday_comes_through(self):
        self.run_payday()   # first

        self.alice.set_tip_to(self.carl, '5.00')
        self.bob.set_tip_to(self.carl, '0.00')

        self.run_payday()   # second

        expected = [
            {"date": today(), "npatrons": 1, "receipts": 5.00},  # most recent first
            {"date": today(), "npatrons": 2, "receipts": 3.00},
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)

        assert actual == expected

    def test_sandwiched_tipless_payday_comes_through(self):
        self.run_payday()   # first

        # Oops! Sorry, Carl. :-(
        self.alice.set_tip_to(self.carl, '0.00')
        self.bob.set_tip_to(self.carl, '0.00')
        self.run_payday()   # second

        # Bouncing back ...
        self.alice.set_tip_to(self.carl, '5.00')
        self.run_payday()   # third

        expected = [
            {"date": today(), "npatrons": 1, "receipts": 5.00},  # most recent first
            {"date": today(), "npatrons": 0, "receipts": 0.00},
            {"date": today(), "npatrons": 2, "receipts": 3.00},
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)

        assert actual == expected

    def test_out_of_band_transfer_gets_included_with_prior_payday(self):
        self.run_payday()   # first
        self.run_payday()   # second

        # Do an out-of-band transfer.
        self.make_transfer(self.alice.id, self.carl.id, 4)

        self.run_payday()   # third

        expected = [
            {
                "date": today(),
                "npatrons": 2,  # most recent first
                "receipts": 3.00,
            },
            {
                "date": today(),
                "npatrons": 2,
                "receipts": 7.00,
            },
            {
                "date": today(),
                "npatrons": 2,
                "receipts": 3.00,
            },
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)

        assert actual == expected

    def test_never_received_gives_empty_array(self):
        self.run_payday()   # first
        self.run_payday()   # second
        self.run_payday()   # third

        expected = []
        actual = json.loads(self.client.GET('/alice/charts.json').text)

        assert actual == expected

    def test_charts_work_for_teams(self):
        team = self.make_participant('team', kind='group')
        team.set_take_for(self.bob, 0.1, team)
        team.set_take_for(self.carl, 1, team)
        self.alice.set_tip_to(team, '0.30')
        self.bob.set_tip_to(team, '0.59')

        self.run_payday()

        expected = [{"date": today(), "npatrons": 2, "receipts": 0.89}]
        actual = json.loads(self.client.GET('/team/charts.json').text)

        assert actual == expected

    def test_transfer_volume(self):
        dana = self.make_participant('dana')
        dana.close(None)

        self.run_payday()
        self.run_payday()

        expected = {
            "date": today(),
            "transfer_volume": '3.00',
            "nactive": '3',
            "nparticipants": '4',
            "nusers": '4',
            "week_deposits": '0.00',
            "week_withdrawals": '0.00',
            "xTitle": utcnow().strftime('%Y-%m-%d'),
        }
        actual = json.loads(self.client.GET('/about/charts.json').text)[0]

        assert actual == expected

    def test_anonymous_receiver(self):
        self.run_payday()
        self.run_payday()
        self.client.PxST('/carl/settings/edit',
                         {'privacy': 'hide_receiving', 'hide_receiving': 'on'},
                         auth_as=self.carl)

        r = self.client.GxT('/carl/charts.json')
        assert r.code == 403

        r = self.client.GxT('/carl/charts.json', auth_as=self.alice)
        assert r.code == 403
