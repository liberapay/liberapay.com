from __future__ import unicode_literals
from nose.tools import assert_equal, assert_true

import pytz
import base64
import json

from aspen.utils import utcnow
from gittip.testing import Harness
from gittip.testing.client import TestClient

class TestCommunitiesJson(Harness):

    def make_client_and_csrf(self):
        client = TestClient()

        csrf_token = client.get('/').request.context['csrf_token']

        return client, csrf_token


    def test_post_name_pattern_none_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        response = client.post('/for/communities.json'
            , { 'name': 'BadName!'
              , 'csrf_token': csrf_token
            }
        )

        actual = response.code

        assert actual == 400, actual

    def test_post_is_member_not_bool_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        response = client.post('/for/communities.json'
            , { 'name': 'Good Name'
              , 'is_member': 'no'
              , 'csrf_token': csrf_token
            }
        )

        actual = response.code

        assert actual == 400, actual

    def test_post_can_join_community(self):
        client, csrf_token = self.make_client_and_csrf()
        community = 'Test'

        self.make_participant("alice", claimed_time=utcnow())

        response = client.get('/for/communities.json', 'alice')

        actual = len(json.loads(response.body)['communities'])
        assert actual == 0, actual

        response = client.post('/for/communities.json'
            , { 'name': community
              , 'is_member': 'true'
              , 'csrf_token': csrf_token
            }
            , user='alice'
        )

        communities = json.loads(response.body)['communities']

        actual = len(communities)
        assert actual == 1, actual

        actual = communities[0]['name']
        assert actual == community, actual

    def test_post_can_leave_community(self):
        client, csrf_token = self.make_client_and_csrf()
        community = 'Test'

        self.make_participant("alice", claimed_time=utcnow())

        response = client.post('/for/communities.json'
            , { 'name': community
              , 'is_member': 'true'
              , 'csrf_token': csrf_token
            }
            , user='alice'
        )

        response = client.post('/for/communities.json'
            , { 'name': community
              , 'is_member': 'false'
              , 'csrf_token': csrf_token
            }
            , user='alice'
        )

        response = client.get('/for/communities.json', 'alice')

        actual = len(json.loads(response.body)['communities'])
        assert actual == 0, actual

    def test_get_can_get_communities_for_user(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_participant("alice", claimed_time=utcnow())

        response = client.get('/for/communities.json', 'alice')

        actual = len(json.loads(response.body)['communities'])
        assert actual == 0, actual

    def test_get_can_get_communities_when_anon(self):
        client, csrf_token = self.make_client_and_csrf()

        response = client.get('/for/communities.json')

        actual = response.code
        assert actual == 200, actual

        actual = len(json.loads(response.body)['communities'])
        assert actual == 0, actual