import json

from liberapay.testing import EUR, Harness


class Tests(Harness):

    def set_up(self, tip_amount=EUR('1.00'), payin_amount=EUR('10.00')):
        self.alice = self.make_participant('alice')
        self.bob = self.make_participant(
            'bob', main_currency='USD', accepted_currencies='EUR,USD',
        )
        self.add_payment_account(self.bob, 'stripe')
        self.alice.set_tip_to(self.bob, tip_amount)
        self.alice_card = self.upsert_route(self.alice, 'stripe-card')
        if payin_amount:
            self.make_payin_and_transfer(self.alice_card, self.bob, payin_amount)

    def test_giving_and_receiving(self):
        self.set_up()

        data_alice = json.loads(self.client.GET('/alice/public.json').text)
        assert data_alice['giving'] == {"amount": "1.00", "currency": "EUR"}
        assert data_alice['receiving'] == {"amount": "0.00", "currency": "EUR"}

        data_bob = json.loads(self.client.GET('/bob/public.json').text)
        assert data_bob['giving'] == {"amount": "0.00", "currency": "USD"}
        assert data_bob['receiving'] == {"amount": "1.20", "currency": "USD"}

        # Hide alice's giving
        r = self.client.PxST(
            '/alice/edit/privacy',
            {'privacy': 'hide_giving', 'hide_giving': 'on'},
            auth_as=self.alice,
        )
        assert r.code == 302

        data_alice = json.loads(self.client.GET('/alice/public.json').text)
        assert data_alice['giving'] is None
        assert data_alice['receiving'] == {"amount": "0.00", "currency": "EUR"}

        # Hide alice's receiving
        r = self.client.PxST(
            '/alice/edit/privacy',
            {'privacy': 'hide_receiving', 'hide_receiving': 'on'},
            auth_as=self.alice,
        )
        assert r.code == 302

        data_alice = json.loads(self.client.GET('/alice/public.json').text)
        assert data_alice['giving'] is None
        assert data_alice['receiving'] is None

    def test_goal_is_undefined_if_user_goal_is_zero(self):
        self.make_participant('alice', goal=EUR(0))
        data = json.loads(self.client.GET('/alice/public.json').text)
        assert 'goal' not in data

    def test_goal_is_null_if_user_has_no_goal(self):
        self.make_participant('alice')
        data = json.loads(self.client.GET('/alice/public.json').text)
        assert data['goal'] == None

    def test_goal_is_a_dict_if_set(self):
        self.make_participant('alice', goal=EUR('1.00'))
        data = json.loads(self.client.GET('/alice/public.json').text)
        assert data['goal'] == {"amount": "1.00", "currency": "EUR"}

    def test_access_control_allow_origin_header_is_asterisk(self):
        self.make_participant('alice')
        response = self.client.GET('/alice/public.json')
        assert response.headers[b'Access-Control-Allow-Origin'] == b'*'
