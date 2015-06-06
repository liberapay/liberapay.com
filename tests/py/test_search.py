from __future__ import unicode_literals

import json

from liberapay.testing import Harness

class TestSearch(Harness):

    def test_get_non_existent_user(self):
        response = self.client.GET('/search.json?q=alice&scope=usernames')
        data = json.loads(response.body)['usernames']
        assert data == []

    def test_get_existing_user(self):
        self.make_participant('alice')
        response = self.client.GET('/search.json?q=alice&scope=usernames')
        data = json.loads(response.body)['usernames']
        assert len(data) == 1
        assert data[0]['username'] == 'alice'

    def test_get_stub_user(self):
        self.make_stub(username='alice')
        response = self.client.GET('/search.json?q=ali&scope=usernames')
        data = json.loads(response.body)['usernames']
        assert data == []

    def test_get_fuzzy_match(self):
        self.make_participant('alice')
        response = self.client.GET('/search.json?q=alicia&scope=usernames')
        data = json.loads(response.body)['usernames']
        assert len(data) == 1
        assert data[0]['username'] == 'alice'

    def test_hide_from_search(self):
        self.make_participant('alice', hide_from_search=True)
        response = self.client.GET('/search.json?q=alice&scope=usernames')
        data = json.loads(response.body)['usernames']
        assert data == []
