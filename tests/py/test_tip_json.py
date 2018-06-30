from __future__ import print_function, unicode_literals

import json

from liberapay.testing import EUR, Harness


class TestTipJson(Harness):

    def tip(self, tipper, tippee, amount, period='weekly', raise_immediately=True):
        data = {'amount': amount, 'period': period}
        return self.client.POST(
            "/%s/tip.json" % tippee,
            data,
            auth_as=tipper,
            xhr=True,
            raise_immediately=raise_immediately,
        )

    def test_get_amount_and_total_back_from_api(self):
        "Test that we get correct amounts and totals back on POSTs to tip.json"

        # First, create some test data
        # We need accounts
        self.make_participant("test_tippee1")
        self.make_participant("test_tippee2")
        test_tipper = self.make_participant("test_tipper", balance=EUR(100))

        # Then, add a $1.50 and $3.00 tip
        response1 = self.tip(test_tipper, "test_tippee1", "1.00")
        response2 = self.tip(test_tipper, "test_tippee2", "3.00")

        # Confirm we get back the right amounts.
        first_data = json.loads(response1.text)
        second_data = json.loads(response2.text)
        assert first_data['amount'] == {"amount": "1.00", "currency": "EUR"}
        assert first_data['total_giving'] == {"amount": "1.00", "currency": "EUR"}
        assert second_data['amount'] == {"amount": "3.00", "currency": "EUR"}
        assert second_data['total_giving'] == {"amount": "4.00", "currency": "EUR"}

    def test_set_tip_out_of_range(self):
        self.make_participant("alice")
        bob = self.make_participant("bob")

        response = self.tip(bob, "alice", "110.00", raise_immediately=False)
        assert "not a valid weekly donation amount" in response.text
        assert response.code == 400

        response = self.tip(bob, "alice", "-1.00", raise_immediately=False)
        assert "not a valid weekly donation amount" in response.text
        assert response.code == 400

        response = self.tip(bob, "alice", "0.01", period='monthly', raise_immediately=False)
        assert "not a valid monthly donation amount" in response.text
        assert response.code == 400

        response = self.tip(bob, "alice", "10000000", period='yearly', raise_immediately=False)
        assert "not a valid yearly donation amount" in response.text
        assert response.code == 400

    def test_set_tip_to_patron(self):
        self.make_participant("alice", goal=EUR(-1))
        bob = self.make_participant("bob")

        response = self.tip(bob, "alice", "10.00", raise_immediately=False)
        assert "doesn't accept donations" in response.text, response.text
        assert response.code == 403

    def test_tip_to_unclaimed(self):
        alice = self.make_elsewhere('twitter', 1, 'alice')
        bob = self.make_participant("bob")
        response = self.tip(bob, alice.participant.username, "10.00")
        data = json.loads(response.text)
        assert response.code == 200
        assert data['amount'] == {"amount": "10.00", "currency": "EUR"}
        assert "alice" in data['msg']

        # Stop pledging
        response = self.tip(bob, alice.participant.username, "0.00")
        data = json.loads(response.text)
        assert response.code == 200
        assert data['amount'] == {"amount": "0.00", "currency": "EUR"}
        assert "alice" in data['msg']

    def test_set_tip_standard_amount(self):
        alice = self.make_participant("alice")
        self.make_participant("bob")

        r = self.client.POST(
            "/bob/tip.json",
            {'selected_amount': '1.00'},
            auth_as=alice,
            xhr=True,
        )
        assert r.code == 200
        r_data = json.loads(r.text)
        assert r_data['amount'] == {"amount": "1.00", "currency": "EUR"}
