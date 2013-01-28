import json

from gittip.testing import Harness
from gittip.testing.client import TestClient


class Tests(Harness):

    def test_anonymous_gets_receiving(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')

        alice.set_tip_to('bob', '1.00')

        actual = json.loads(TestClient().get('/bob/public.json').body)
        expected = {'receiving': '1.00'}
        assert actual == expected, actual

    def test_authenticated_user_gets_their_tip(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')

        alice.set_tip_to('bob', '1.00')

        raw = TestClient().get('/bob/public.json', user='alice').body

        actual = json.loads(raw)
        expected = {'receiving': '1.00', 'my_tip': '1.00'}
        assert actual == expected, actual

    def test_authenticated_user_doesnt_get_other_peoples_tips(self):
        alice = self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob', last_bill_result='')
        carl = self.make_participant('carl', last_bill_result='')
        self.make_participant('dana')

        alice.set_tip_to('dana', '1.00')
        bob.set_tip_to('dana', '3.00')
        carl.set_tip_to('dana', '12.00')

        raw = TestClient().get('/dana/public.json', user='alice').body

        actual = json.loads(raw)
        expected = {'receiving': '16.00', 'my_tip': '1.00'}
        assert actual == expected, actual

    def test_authenticated_user_gets_zero_if_they_dont_tip(self):
        self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob', last_bill_result='')
        self.make_participant('carl')

        bob.set_tip_to('carl', '3.00')

        raw = TestClient().get('/carl/public.json', user='alice').body

        actual = json.loads(raw)
        expected = {'receiving': '3.00', 'my_tip': '0.00'}
        assert actual == expected, actual

    def test_authenticated_user_gets_self_for_self(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')

        alice.set_tip_to('bob', '3.00')

        raw = TestClient().get('/bob/public.json', user='bob').body

        actual = json.loads(raw)
        expected = {'receiving': '3.00', 'my_tip': 'self'}
        assert actual == expected, actual
