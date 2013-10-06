from __future__ import division, print_function, unicode_literals

import mock
from gittip.testing import Harness, test_website as _test_website
from gittip.testing.client import TestClient


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.website = _test_website
        self.client = TestClient()

    def tearDown(self):
        Harness.tearDown(self)
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


    @mock.patch('requests.post')
    @mock.patch('requests.get')
    @mock.patch('gittip.utils.mixpanel.track')
    def test_associate_confirms_on_connect(self, track, get, post):
        self.make_user('alice', user_info={'id': 1234})

        self.make_participant('bob')
        self.website.oauth_cache = {"deadbeef": ("deadbeef", "connect", "")}

        post.return_value.status_code = 200
        post.return_value.text = "oauth_token=foo&oauth_token_secret=foo&user_id=foo"

        get.return_value.status_code = 200
        get.return_value.text = '{"id": 1234, "screen_name": "alice"}'

        self.client.get('/') # populates cookies['csrf_token']
        response = self.client.get("/on/twitter/associate?oauth_token=deadbeef&"
                                   "oauth_verifier=donald_trump", user="bob")
        assert "Please Confirm" in response.body, response.body


    @mock.patch('requests.post')
    @mock.patch('requests.get')
    @mock.patch('gittip.utils.mixpanel.track')
    def test_confirmation_properly_displays_remaining_bitbucket(self, track, get, post):
        alice, foo = TwitterAccount('1234', {'screen_name': 'alice'}).opt_in('alice')
        alice.participant.take_over(BitbucketAccount('1234', {'username': 'alice_bb'}))

        self.make_participant('bob')
        self.website.oauth_cache = {"deadbeef": ("deadbeef", "connect", "")}

        post.return_value.status_code = 200
        post.return_value.text = "oauth_token=foo&oauth_token_secret=foo&user_id=foo"

        get.return_value.status_code = 200
        get.return_value.text = '{"id": 1234, "screen_name": "alice"}'

        self.client.get('/') # populates cookies['csrf_token']
        response = self.client.get("/on/twitter/associate?oauth_token=deadbeef&"
                                   "oauth_verifier=donald_trump", user="bob")
        assert response.body.count("alice_bb<br />") == 2, response.body


    def test_can_post_to_take_over(self):
        TwitterAccount('1234', {'screen_name': 'alice'}).opt_in('alice')

        self.make_participant('bob')
        self.website.connect_tokens = {("bob", "twitter", "1234"): "deadbeef"}

        csrf_token = self.client.get('/').request.context['csrf_token']
        response = self.client.post( "/on/take-over.html"
                                   , data={ "platform": "twitter"
                                          , "user_id": "1234"
                                          , "csrf_token": csrf_token
                                          , "connect_token": "deadbeef"
                                          , "should_reconnect": "yes"
                                           }
                                   , user="bob"
                                    )

        assert response.code == 302, response.body
        expected = '/about/me.html'
        actual = response.headers['Location']
        assert actual == expected
