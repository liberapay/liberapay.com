from __future__ import unicode_literals

import json

from aspen.utils import utcnow
from gittip.testing import Harness

class TestLookupJson(Harness):

    def test_get_without_query_querystring_returns_400(self):
        response = self.client.GET('/lookup.json')
        assert response.code == 400

    def test_get_non_existent_user(self):
        response = self.client.GET('/lookup.json?query={}'.format('alice'))
        data = json.loads(response.body)

        assert len(data) == 1
        assert data[0]['id'] == -1

    def test_get_existing_user(self):
        self.make_participant("alice", claimed_time=utcnow())

        response = self.client.GET('/lookup.json?query={}'.format('alice'))
        data = json.loads(response.body)

        assert len(data) == 1
        assert data[0]['id'] != -1
