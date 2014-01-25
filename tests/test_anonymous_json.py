from __future__ import print_function, unicode_literals

from aspen import json
from gittip.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.make_participant('alice')

    def hit_anonymous(self, method='GET', expected_code=200, **kw):
        response = self.client.hit(method, "/alice/anonymous.json", auth_as='alice', **kw)
        if response.code != expected_code:
            print(response.body)
        return response


    def test_participant_can_get_their_anonymity_settings(self):
        response = self.hit_anonymous('GET')
        actual = json.loads(response.body)
        assert actual == {'giving': False, 'receiving': False}

    def test_participant_can_toggle_anonymous_giving(self):
        response = self.hit_anonymous('POST', data={'toggle': 'giving'})
        actual = json.loads(response.body)
        assert actual['giving'] is True

    def test_participant_can_toggle_anonymous_receiving(self):
        response = self.hit_anonymous('POST', data={'toggle': 'receiving'})
        actual = json.loads(response.body)
        assert actual['receiving'] is True

    def test_participant_can_toggle_anonymous_giving_back(self):
        response = self.hit_anonymous('POST', data={'toggle': 'giving'})
        response = self.hit_anonymous('POST', data={'toggle': 'giving'})
        actual = json.loads(response.body)['giving']
        assert actual is False

    def test_participant_can_toggle_anonymous_receiving_back(self):
        response = self.hit_anonymous('POST', data={'toggle': 'receiving'})
        response = self.hit_anonymous('POST', data={'toggle': 'receiving'})
        actual = json.loads(response.body)['receiving']
        assert actual is False
