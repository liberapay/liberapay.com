import json

from liberapay.models.community import Community
from liberapay.testing import Harness

class TestSearch(Harness):

    def test_basic_search(self):
        response = self.client.GET('/search?q=foobar')
        assert response.code == 200

    def test_basic_search_with_results(self):
        alice = self.make_participant('alice')
        Community.create('alice', alice)
        response = self.client.GET('/search?q=alice')
        assert response.code == 200
        assert 'alice' in response.text

    def test_get_non_existent_user(self):
        response = self.client.GET('/search.json?q=alice&scope=usernames')
        data = json.loads(response.text)['usernames']
        assert data == []

    def test_get_existing_user(self):
        self.make_participant('alice')
        response = self.client.GET('/search.json?q=alice&scope=usernames')
        data = json.loads(response.text)['usernames']
        assert len(data) == 1
        assert data[0]['username'] == 'alice'

    def test_get_stub_user(self):
        self.make_stub(username='alice')
        response = self.client.GET('/search.json?q=ali&scope=usernames')
        data = json.loads(response.text)['usernames']
        assert data == []

    def test_get_fuzzy_match(self):
        self.make_participant('alice')
        response = self.client.GET('/search.json?q=alicia&scope=usernames')
        data = json.loads(response.text)['usernames']
        assert len(data) == 1
        assert data[0]['username'] == 'alice'

    def test_hide_from_search(self):
        self.make_participant('alice', hide_from_search=1)
        response = self.client.GET('/search.json?q=alice&scope=usernames')
        data = json.loads(response.text)['usernames']
        assert data == []

    def test_search_unknown_languages(self):
        alice = self.make_participant('alice')
        alice.upsert_statement('en', "Foobar")
        response = self.client.GET(
            '/search.json?q=foobar', HTTP_ACCEPT_LANGUAGE="xxa,xxb,xxc,xxd,xxe"
        )
        data = json.loads(response.text)
        assert len(data['statements']) == 1

    def test_html_is_returned_to_client_requesting_anything(self):
        r = self.client.GET('/search?q=something', HTTP_ACCEPT=b'*/*')
        assert r.code == 200
        assert r.headers[b'Content-Type'] == b'text/html; charset=UTF-8'
