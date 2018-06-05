from __future__ import print_function, unicode_literals

import json

from liberapay.testing import EUR, Harness


class Tests(Harness):

    def test_anonymous(self):
        alice = self.make_participant('alice', balance=EUR(100))
        bob = self.make_participant('bob')

        alice.set_tip_to(bob, EUR('1.00'))

        data = json.loads(self.client.GET('/bob/public.json').text)
        assert data['receiving'] == {"amount": "1.00", "currency": "EUR"}
        assert 'my_tip' not in data

        data = json.loads(self.client.GET('/alice/public.json').text)
        assert data['giving'] == {"amount": "1.00", "currency": "EUR"}

    def test_anonymous_gets_null_giving_if_user_anonymous(self):
        alice = self.make_participant('alice', balance=EUR(100), hide_giving=True)
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, EUR('1.00'))
        data = json.loads(self.client.GET('/alice/public.json').text)

        assert data['giving'] == None

    def test_anonymous_gets_null_receiving_if_user_anonymous(self):
        alice = self.make_participant('alice', balance=EUR(100), hide_receiving=True)
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, EUR('1.00'))
        data = json.loads(self.client.GET('/alice/public.json').text)

        assert data['receiving'] == None

    def test_anonymous_does_not_get_goal_if_user_regifts(self):
        self.make_participant('alice', balance=EUR(100), goal=EUR(0))
        data = json.loads(self.client.GET('/alice/public.json').text)
        assert 'goal' not in data

    def test_anonymous_gets_null_goal_if_user_has_no_goal(self):
        self.make_participant('alice', balance=EUR(100))
        data = json.loads(self.client.GET('/alice/public.json').text)
        assert data['goal'] == None

    def test_anonymous_gets_user_goal_if_set(self):
        self.make_participant('alice', balance=EUR(100), goal=EUR('1.00'))
        data = json.loads(self.client.GET('/alice/public.json').text)
        assert data['goal'] == {"amount": "1.00", "currency": "EUR"}

    def test_access_control_allow_origin_header_is_asterisk(self):
        self.make_participant('alice', balance=EUR(100))
        response = self.client.GET('/alice/public.json')

        assert response.headers[b'Access-Control-Allow-Origin'] == b'*'
