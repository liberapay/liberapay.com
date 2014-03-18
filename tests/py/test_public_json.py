from __future__ import print_function, unicode_literals

import json
import datetime

import pytz
from gittip.testing import Harness


class Tests(Harness):

    def make_participant(self, *a, **kw):
        kw['claimed_time'] = datetime.datetime.now(pytz.utc)
        return Harness.make_participant(self, *a, **kw)

    def test_on_key_gives_gittip(self):
        self.make_participant('alice', last_bill_result='')
        data = json.loads(self.client.GET('/alice/public.json').body)

        assert data['on'] == 'gittip'

    def test_anonymous_gets_receiving(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')

        alice.set_tip_to('bob', '1.00')

        data = json.loads(self.client.GET('/bob/public.json').body)

        assert data['receiving'] == '1.00'

    def test_anonymous_does_not_get_my_tip(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')

        alice.set_tip_to('bob', '1.00')

        data = json.loads(self.client.GET('/bob/public.json').body)

        assert data.has_key('my_tip') == False

    def test_anonymous_gets_giving(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')

        alice.set_tip_to('bob', '1.00')

        data = json.loads(self.client.GET('/alice/public.json').body)

        assert data['giving'] == '1.00'

    def test_anonymous_gets_null_giving_if_user_anonymous(self):
        alice = self.make_participant( 'alice'
                                     , last_bill_result=''
                                     , anonymous_giving=True
                                     )
        self.make_participant('bob')
        alice.set_tip_to('bob', '1.00')
        data = json.loads(self.client.GET('/alice/public.json').body)

        assert data['giving'] == None

    def test_anonymous_gets_null_receiving_if_user_anonymous(self):
        alice = self.make_participant( 'alice'
                                     , last_bill_result=''
                                     , anonymous_receiving=True
                                     )
        self.make_participant('bob')
        alice.set_tip_to('bob', '1.00')
        data = json.loads(self.client.GET('/alice/public.json').body)

        assert data['receiving'] == None

    def test_anonymous_does_not_get_goal_if_user_regifts(self):
        self.make_participant('alice', last_bill_result='', goal=0)
        data = json.loads(self.client.GET('/alice/public.json').body)
        assert data.has_key('goal') == False

    def test_anonymous_gets_null_goal_if_user_has_no_goal(self):
        self.make_participant('alice', last_bill_result='')
        data = json.loads(self.client.GET('/alice/public.json').body)
        assert data['goal'] == None

    def test_anonymous_gets_user_goal_if_set(self):
        self.make_participant('alice', last_bill_result='', goal=1)
        data = json.loads(self.client.GET('/alice/public.json').body)
        assert data['goal'] == '1.00'

    def test_authenticated_user_gets_their_tip(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')

        alice.set_tip_to('bob', '1.00')

        raw = self.client.GET('/bob/public.json', auth_as='alice').body

        data = json.loads(raw)

        assert data['receiving'] == '1.00'
        assert data['my_tip'] == '1.00'

    def test_authenticated_user_doesnt_get_other_peoples_tips(self):
        alice = self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob', last_bill_result='')
        carl = self.make_participant('carl', last_bill_result='')
        self.make_participant('dana')

        alice.set_tip_to('dana', '1.00')
        bob.set_tip_to('dana', '3.00')
        carl.set_tip_to('dana', '12.00')

        raw = self.client.GET('/dana/public.json', auth_as='alice').body

        data = json.loads(raw)

        assert data['receiving'] == '16.00'
        assert data['my_tip'] == '1.00'

    def test_authenticated_user_gets_zero_if_they_dont_tip(self):
        self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob', last_bill_result='')
        self.make_participant('carl')

        bob.set_tip_to('carl', '3.00')

        raw = self.client.GET('/carl/public.json', auth_as='alice').body

        data = json.loads(raw)

        assert data['receiving'] == '3.00'
        assert data['my_tip'] == '0.00'

    def test_authenticated_user_gets_self_for_self(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')

        alice.set_tip_to('bob', '3.00')

        raw = self.client.GET('/bob/public.json', auth_as='bob').body

        data = json.loads(raw)

        assert data['receiving'] == '3.00'
        assert data['my_tip'] == 'self'
