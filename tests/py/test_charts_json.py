import json

from liberapay.billing.payday import Payday
from liberapay.testing import EUR, Harness


def date(payday):
    return payday.ts_start.strftime('%Y-%m-%d')


class TestChartsJson(Harness):

    def setUp(self):
        super().setUp()

        self.alice = self.make_participant('alice')
        self.bob = self.make_participant('bob')
        self.carl = self.make_participant('carl')
        self.make_participant('notactive')

        self.alice.set_tip_to(self.carl, EUR('1.00'))
        self.alice_card = self.upsert_route(self.alice, 'stripe-card')
        self.make_payin_and_transfer(self.alice_card, self.carl, EUR('10.00'))
        self.bob.set_tip_to(self.carl, EUR('2.00'))
        self.bob_card = self.upsert_route(self.bob, 'stripe-card')
        self.make_payin_and_transfer(self.bob_card, self.carl, EUR('10.00'))

    def run_payday(self):
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")
        payday = Payday.start()
        payday.run(recompute_stats=1)
        return payday

    def test_no_payday_returns_empty_list(self):
        assert json.loads(self.client.GxT('/carl/charts.json').text) == []

    def test_first_payday_comes_through(self):
        payday = self.run_payday()
        expected = [
            {"date": date(payday), "npatrons": 2, "receipts": {"amount": "3.00", "currency": "EUR"}},
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)
        assert actual == expected

    def test_second_payday_comes_through(self):
        self.alice.set_tip_to(self.carl, EUR('10.00'))
        payday_1 = self.run_payday()


        payday_2 = self.run_payday()

        expected = [
            {"date": date(payday_2), "npatrons": 1, "receipts": {"amount": "2.00", "currency": "EUR"}},
            {"date": date(payday_1), "npatrons": 2, "receipts": {"amount": "12.00", "currency": "EUR"}},
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)
        assert actual == expected

    def test_sandwiched_tipless_payday_comes_through(self):
        self.alice.set_tip_to(self.carl, EUR('10.00'))
        self.bob.set_tip_to(self.carl, EUR('10.00'))
        payday_1 = self.run_payday()
        payday_2 = self.run_payday()

        # Bouncing back ...
        self.alice.set_tip_to(self.carl, EUR('5.00'))
        self.make_payin_and_transfer(self.alice_card, self.carl, EUR('10.00'))
        payday_3 = self.run_payday()

        expected = [
            {"date": date(payday_3), "npatrons": 1, "receipts": {"amount": "5.00", "currency": "EUR"}},
            {"date": date(payday_2), "npatrons": 0, "receipts": {"amount": "0.00", "currency": "EUR"}},
            {"date": date(payday_1), "npatrons": 2, "receipts": {"amount": "20.00", "currency": "EUR"}},
        ]
        actual = json.loads(self.client.GET('/carl/charts.json').text)
        assert actual == expected

    def test_never_received_gives_empty_array(self):
        self.run_payday()
        self.run_payday()
        self.run_payday()

        expected = []
        actual = json.loads(self.client.GxT('/alice/charts.json').text)
        assert actual == expected

    def test_charts_work_for_teams(self):
        team = self.make_participant('team', kind='group')
        team.set_take_for(self.bob, EUR('0.10'), team)
        team.set_take_for(self.carl, EUR('1.00'), team)
        self.alice.set_tip_to(team, EUR('0.30'))
        self.bob.set_tip_to(team, EUR('0.59'))
        self.make_payin_and_transfer(self.alice_card, team, EUR('4.00'))
        self.make_payin_and_transfer(self.bob_card, team, EUR('6.00'))

        payday = self.run_payday()

        expected = [
            {"date": date(payday), "npatrons": 2, "receipts": {"amount": "0.89", "currency": "EUR"}},
        ]
        actual = json.loads(self.client.GET('/team/charts.json').text)
        assert actual == expected

    def test_transfer_volume(self):
        dana = self.make_participant('dana')
        dana.close()

        self.run_payday()
        payday_2 = self.run_payday()

        zero = {'amount': '0.00', 'currency': 'EUR'}
        expected = {
            "date": date(payday_2),
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
        r = self.client.PxST(
            '/carl/edit/privacy',
            {'privacy': 'hide_receiving', 'hide_receiving': 'on'},
            auth_as=self.carl,
        )
        assert r.code == 302

        r = self.client.GxT('/carl/charts.json')
        assert r.code == 403

        r = self.client.GxT('/carl/charts.json', auth_as=self.alice)
        assert r.code == 403
