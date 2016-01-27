from __future__ import print_function, unicode_literals

import json

from liberapay.testing import Harness


class Tests(Harness):

    def test_anonymous(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')

        alice.set_tip_to(bob, '1.00')

        data = json.loads(self.client.GET('/bob/public.json').body)
        assert data['receiving'] == '1.00'
        assert 'my_tip' not in data

        data = json.loads(self.client.GET('/alice/public.json').body)
        assert data['giving'] == '1.00'

    def test_anonymous_gets_null_giving_if_user_anonymous(self):
        alice = self.make_participant( 'alice'
                                     , balance=100
                                     , hide_giving=True
                                     )
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, '1.00')
        data = json.loads(self.client.GET('/alice/public.json').body)

        assert data['giving'] == None

    def test_anonymous_gets_null_receiving_if_user_anonymous(self):
        alice = self.make_participant( 'alice'
                                     , balance=100
                                     , hide_receiving=True
                                     )
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, '1.00')
        data = json.loads(self.client.GET('/alice/public.json').body)

        assert data['receiving'] == None

    def test_anonymous_does_not_get_goal_if_user_regifts(self):
        self.make_participant('alice', balance=100, goal=0)
        data = json.loads(self.client.GET('/alice/public.json').body)
        assert 'goal' not in data

    def test_anonymous_gets_null_goal_if_user_has_no_goal(self):
        self.make_participant('alice', balance=100)
        data = json.loads(self.client.GET('/alice/public.json').body)
        assert data['goal'] == None

    def test_anonymous_gets_user_goal_if_set(self):
        self.make_participant('alice', balance=100, goal=1)
        data = json.loads(self.client.GET('/alice/public.json').body)
        assert data['goal'] == '1.00'

    def test_authenticated_user_gets_their_tip(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')

        alice.set_tip_to(bob, '1.00')

        raw = self.client.GET('/bob/public.json', auth_as=alice).body

        data = json.loads(raw)

        assert data['receiving'] == '1.00'
        assert data['my_tip'] == '1.00'

    def test_authenticated_user_doesnt_get_other_peoples_tips(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob', balance=100)
        carl = self.make_participant('carl', balance=100)
        dana = self.make_participant('dana')

        alice.set_tip_to(dana, '1.00')
        bob.set_tip_to(dana, '3.00')
        carl.set_tip_to(dana, '12.00')

        raw = self.client.GET('/dana/public.json', auth_as=alice).body

        data = json.loads(raw)

        assert data['receiving'] == '16.00'
        assert data['my_tip'] == '1.00'

    def test_authenticated_user_gets_zero_if_they_dont_tip(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob', balance=100)
        carl = self.make_participant('carl')

        bob.set_tip_to(carl, '3.00')

        raw = self.client.GET('/carl/public.json', auth_as=alice).body

        data = json.loads(raw)

        assert data['receiving'] == '3.00'
        assert data['my_tip'] == '0.00'

    def test_authenticated_user_gets_self_for_self(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')

        alice.set_tip_to(bob, '3.00')

        raw = self.client.GET('/bob/public.json', auth_as=bob).body

        data = json.loads(raw)

        assert data['receiving'] == '3.00'
        assert data['my_tip'] == 'self'

    def test_access_control_allow_origin_header_is_asterisk(self):
        self.make_participant('alice', balance=100)
        response = self.client.GET('/alice/public.json')

        assert response.headers['Access-Control-Allow-Origin'] == '*'

    def test_jsonp_works(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')

        alice.set_tip_to(bob, '3.00')

        raw = self.client.GET('/bob/public.json?callback=foo', auth_as=bob).body

        assert raw == '''\
/**/ foo({
    "avatar": null,
    "elsewhere": {
        "github": {
            "id": %(elsewhere_id)s,
            "user_id": "%(user_id)s",
            "user_name": "bob"
        }
    },
    "giving": "0.00",
    "goal": null,
    "id": %(user_id)s,
    "kind": "individual",
    "my_tip": "self",
    "npatrons": 1,
    "receiving": "3.00",
    "username": "bob"
});''' % dict(user_id=bob.id, elsewhere_id=bob.get_accounts_elsewhere()['github'].id)
