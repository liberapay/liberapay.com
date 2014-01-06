from __future__ import print_function, unicode_literals

from aspen import json
from gittip.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.make_participant('alice')

    def hit_anonymous(self, method='GET', expected_code=200):
        response = self.client.hit(method, "/alice/anonymous.json", auth_as='alice')
        if response.code != expected_code:
            print(response.body)
        return response


    def test_participant_can_get_their_anonymity_setting(self):
        response = self.hit_anonymous('GET')
        actual = json.loads(response.body)['anonymous']
        assert actual is False

    def test_participant_can_toggle_their_anonymity_setting(self):
        response = self.hit_anonymous('POST')
        actual = json.loads(response.body)['anonymous']
        assert actual is True

    def test_participant_can_toggle_their_anonymity_setting_back(self):
        response = self.hit_anonymous('POST')
        response = self.hit_anonymous('POST')
        actual = json.loads(response.body)['anonymous']
        assert actual is False
