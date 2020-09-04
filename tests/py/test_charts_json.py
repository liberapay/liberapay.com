import datetime
import json

from liberapay.billing.payday import Payday
from liberapay.testing import EUR
from liberapay.testing.mangopay import FakeTransfersHarness


def today():
    return datetime.datetime.utcnow().date().strftime('%Y-%m-%d')


class TestChartsJson(FakeTransfersHarness):

    def setUp(self):
        super().setUp()

        self.alice = self.make_participant('alice')
        self.bob = self.make_participant('bob')
        self.carl = self.make_participant('carl')
        self.make_exchange('mango-cc', 10, 0, self.alice)
        self.make_exchange('mango-cc', 10, 0, self.bob)
        self.make_participant('notactive')

        self.alice.set_tip_to(self.carl, EUR('1.00'))
        self.bob.set_tip_to(self.carl, EUR('2.00'))

    def run_payday(self):
        Payday.start().run(recompute_stats=1)


    def test_no_payday_returns_empty_list(self):
        assert json.loads(self.client.GxT('/carl/charts.json').text) == []

    def test_first_payday_comes_through(self):
        self.run_payday()   # first

        expected = [{"date": today(), "npatrons": 2, "receipts": {"amount": "3.00", "currency": "EUR"}}]
        actual = json.loads(self.client.GET('/carl/charts.json').text)

        assert actual == expected

    def test_second_payday_comes_through(self):
        self.run_payday()   # first

        self.alice.set_tip_to(self.carl, EUR('5.00'))
        self.bob.set_tip_to(self.carl, EUR('0.00'))

        self.run_payday()   # second

        expected = [
            {"date": today(), "npatrons": 1, "receipts": {"amount": "5.00", "currency": "EUR"}},  # most recent first
            {"date": today(), "npatrons": 2, "receipts": {"amount": "3.00", "currency": "EUR"}},
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)

        assert actual == expected

    def test_sandwiched_tipless_payday_comes_through(self):
        self.run_payday()   # first

        # Oops! Sorry, Carl. :-(
        self.alice.set_tip_to(self.carl, EUR('0.00'))
        self.bob.set_tip_to(self.carl, EUR('0.00'))
        self.run_payday()   # second

        # Bouncing back ...
        self.alice.set_tip_to(self.carl, EUR('5.00'))
        self.run_payday()   # third

        expected = [
            {"date": today(), "npatrons": 1, "receipts": {"amount": "5.00", "currency": "EUR"}},  # most recent first
            {"date": today(), "npatrons": 0, "receipts": {"amount": "0.00", "currency": "EUR"}},
            {"date": today(), "npatrons": 2, "receipts": {"amount": "3.00", "currency": "EUR"}},
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)

        assert actual == expected

    def test_out_of_band_transfer_gets_included_with_next_payday(self):
        self.run_payday()   # first

        # Do an out-of-band transfer.
        self.make_transfer(self.alice.id, self.carl.id, EUR('4.00'))

        self.run_payday()   # second
        self.run_payday()   # third

        expected = [
            {
                "date": today(),
                "npatrons": 2,  # most recent first
                "receipts": {"amount": "3.00", "currency": "EUR"},
            },
            {
                "date": today(),
                "npatrons": 2,
                "receipts": {"amount": "7.00", "currency": "EUR"},
            },
            {
                "date": today(),
                "npatrons": 2,
                "receipts": {"amount": "3.00", "currency": "EUR"},
            },
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)

        assert actual == expected

    def test_never_received_gives_empty_array(self):
        self.run_payday()   # first
        self.run_payday()   # second
        self.run_payday()   # third

        expected = []
        actual = json.loads(self.client.GxT('/alice/charts.json').text)

        assert actual == expected

    def test_charts_work_for_teams(self):
        team = self.make_participant('team', kind='group')
        team.set_take_for(self.bob, EUR('0.10'), team)
        team.set_take_for(self.carl, EUR('1.00'), team)
        self.alice.set_tip_to(team, EUR('0.30'))
        self.bob.set_tip_to(team, EUR('0.59'))

        self.run_payday()

        expected = [{"date": today(), "npatrons": 2, "receipts": {"amount": "0.89", "currency": "EUR"}}]
        actual = json.loads(self.client.GET('/team/charts.json').text)

        assert actual == expected

    def test_transfer_volume(self):
        dana = self.make_participant('dana')
        dana.close(None)

        self.run_payday()
        self.run_payday()

        zero = {'amount': '0.00', 'currency': 'EUR'}
        expected = {
            "date": today(),
            "transfer_volume": {'amount': '3.00', 'currency': 'EUR'},
            "nactive": '3',
            "nparticipants": '5',
            "nusers": '4',
            "week_payins": zero,
        }
        actual = json.loads(self.client.GET('/about/charts.json').text)[0]
        assert actual == expected

        Payday.recompute_stats()
        actual = json.loads(self.client.GET('/about/charts.json').text)[0]
        assert actual == expected

    def test_anonymous_receiver(self):
        self.run_payday()
        self.run_payday()
        self.client.PxST('/carl/edit/privacy',
                         {'privacy': 'hide_receiving', 'hide_receiving': 'on'},
                         auth_as=self.carl)

        r = self.client.GxT('/carl/charts.json')
        assert r.code == 403

        r = self.client.GxT('/carl/charts.json', auth_as=self.alice)
        assert r.code == 403
