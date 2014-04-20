from __future__ import unicode_literals

import json

from aspen.utils import utcnow
from gittip.testing import Harness
from gittip.testing.client import TestClient

class TestMembernameJson(Harness):

    def make_client_and_csrf(self):
        client = TestClient()

        csrf_token = client.get('/').request.context['csrf_token']

        return client, csrf_token


    def test_get_returns_405(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_participant("alice", claimed_time=utcnow())

        response = client.get('/alice/email.json')

        actual = response.code
        assert actual == 405, actual

    def test_post_anon_returns_401(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_participant("alice", claimed_time=utcnow())

        response = client.post('/alice/email.json'
            , { 'csrf_token': csrf_token })

        actual = response.code
        assert actual == 401, actual

    def test_post_with_no_email_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_participant("alice", claimed_time=utcnow())

        response = client.post('/alice/email.json'
            , { 'csrf_token': csrf_token }
            , user='alice'
        )

        actual = response.code
        assert actual == 400, actual

    def test_post_with_no_at_in_email_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_participant("alice", claimed_time=utcnow())

        response = client.post('/alice/email.json'
            , {
                'csrf_token': csrf_token
              , 'email': 'bademail.com'
            }
            , user='alice'
        )

        actual = response.code
        assert actual == 400, actual

    def test_post_with_no_dot_in_email_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_participant("alice", claimed_time=utcnow())

        response = client.post('/alice/email.json'
            , {
                'csrf_token': csrf_token
              , 'email': 'bad@emailcom'
            }
            , user='alice'
        )

        actual = response.code
        assert actual == 400, actual

    def test_post_with_good_email_is_success(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_participant("alice", claimed_time=utcnow())

        response = client.post('/alice/email.json'
            , {
                'csrf_token': csrf_token
              , 'email': 'good@gittip.com'
            }
            , user='alice'
        )

        actual = response.code
        assert actual == 200, actual

        actual = json.loads(response.body)['email']
        assert actual == 'good@gittip.com', actual