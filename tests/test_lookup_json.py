from __future__ import unicode_literals
from nose.tools import assert_equal

import json

from aspen.utils import utcnow
from gittip.testing import Harness
from gittip.testing.client import TestClient

class TestLookupJson(Harness):

    def make_client_and_csrf(self):
        client = TestClient()

        csrf_token = client.get('/').request.context['csrf_token']

        return client, csrf_token

    def test_get_without_query_querystring_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        response = client.get('/lookup.json')

        actual = response.code
        assert actual == 400, actual

    def test_get_non_existent_user(self):
        client, csrf_token = self.make_client_and_csrf()

        response = client.get('/lookup.json?query={}'.format('alice'))

        data = json.loads(response.body)

        actual = len(data)
        assert actual == 1, actual

        actual = data[0]['id']
        assert actual == -1, actual

    def test_get_existing_user(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_participant("alice", claimed_time=utcnow())

        response = client.get('/lookup.json?query={}'.format('alice'))

        data = json.loads(response.body)

        actual = len(data)
        assert actual == 1, actual

        actual = data[0]['id']
        assert actual != -1, actual