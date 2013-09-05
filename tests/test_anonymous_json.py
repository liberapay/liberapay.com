from __future__ import print_function, unicode_literals

from aspen import json

from gittip.elsewhere.twitter import TwitterAccount
from gittip.testing import Harness
from gittip.testing.client import TestClient


class Tests(Harness):

    def hit_anonymous(self, method='GET', expected_code=200):
        user, ignored = TwitterAccount('alice', {}).opt_in('alice')

        client = TestClient()
        response = client.get('/')
        csrf_token = response.request.context['csrf_token']

        if method == 'GET':
            response = client.get( "/alice/anonymous.json"
                                 , user='alice'
                                  )
        else:
            assert method == 'POST'
            response = client.post( "/alice/anonymous.json"
                                  , {'csrf_token': csrf_token}
                                  , user='alice'
                                   )
        if response.code != expected_code:
            print(response.body)
        return response


    def test_participant_can_get_their_anonymity_setting(self):
        response = self.hit_anonymous('GET')
        actual = json.loads(response.body)['anonymous']
        assert actual is False, actual

    def test_participant_can_toggle_their_anonymity_setting(self):
        response = self.hit_anonymous('POST')
        actual = json.loads(response.body)['anonymous']
        assert actual is True, actual

    def test_participant_can_toggle_their_anonymity_setting_back(self):
        response = self.hit_anonymous('POST')
        response = self.hit_anonymous('POST')
        actual = json.loads(response.body)['anonymous']
        assert actual is False, actual
