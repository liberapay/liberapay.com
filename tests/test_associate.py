from __future__ import division, print_function, unicode_literals

import mock
from gittip.testing import Harness, test_website
from gittip.testing.client import TestClient


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.website = test_website
        self.client = TestClient()

    def tearDown(self):
        self.website.oauth_cache = {}


    @mock.patch('requests.post')
    @mock.patch('requests.get')
    @mock.patch('gittip.utils.mixpanel.track')
    def test_associate_opts_in(self, track, get, post):
        self.website.oauth_cache = {"deadbeef": ("deadbeef", "opt-in", "")}

        post.return_value.status_code = 200
        post.return_value.text = "oauth_token=foo&oauth_token_secret=foo&user_id=foo"

        get.return_value.status_code = 200
        get.return_value.text = '{"id": 1234, "screen_name": "alice"}'

        response = self.client.get("/on/twitter/associate?oauth_token=deadbeef&"
                                   "oauth_verifier=donald_trump")
        assert response.code == 302, response.body
        assert response.headers['Location'] == "/alice/", response.headers


    @mock.patch('requests.post')
    @mock.patch('requests.get')
    @mock.patch('gittip.utils.mixpanel.track')
    def test_associate_connects(self, track, get, post):
        self.make_participant('alice')
        self.website.oauth_cache = {"deadbeef": ("deadbeef", "connect", "")}

        post.return_value.status_code = 200
        post.return_value.text = "oauth_token=foo&oauth_token_secret=foo&user_id=foo"

        get.return_value.status_code = 200
        get.return_value.text = '{"id": 1234, "screen_name": "alice"}'

        response = self.client.get("/on/twitter/associate?oauth_token=deadbeef&"
                                   "oauth_verifier=donald_trump", user="alice")
        assert response.code == 302, response.body
        assert response.headers['Location'] == "/alice/", response.headers

        rec = self.db.one("SELECT * FROM elsewhere")
        assert rec.participant == 'alice', rec
        assert rec.platform == 'twitter', rec
