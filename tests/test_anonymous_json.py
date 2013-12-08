from __future__ import print_function, unicode_literals

from aspen import json

from gittip.elsewhere.twitter import TwitterAccount
from gittip.testing import Harness


class Tests(Harness):

    def hit_anonymous(self, method='GET', expected_code=200):
        user, ignored = TwitterAccount(self.db, 'alice', {}).opt_in('alice')

        response = self.GET('/')
        csrf_token = response.request.context['csrf_token']

        if method == 'GET':
            response = self.GET("/alice/anonymous.json", user='alice')
        else:
            assert method == 'POST'
            response = self.POST( "/alice/anonymous.json"
                                , {'csrf_token': csrf_token}
                                , user='alice'
                                 )
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
