from __future__ import division, print_function, unicode_literals

import mock
from gittip.testing import Harness
from gittip.elsewhere.bitbucket import BitbucketAccount
from gittip.elsewhere.twitter import TwitterAccount


class Tests(Harness):

    @mock.patch('requests.post')
    @mock.patch('requests.get')
    def test_associate_opts_in(self, get, post):
        self.client.website.oauth_cache = {"deadbeef": ("deadbeef", "opt-in", "")}

        post.return_value.status_code = 200
        post.return_value.text = "oauth_token=foo&oauth_token_secret=foo&screen_name=foo"

        get.return_value.status_code = 200
        get.return_value.text = '{"id": 1234, "screen_name": "alice"}'

        response = self.client.GxT("/on/twitter/associate?oauth_token=deadbeef&"
                                   "oauth_verifier=donald_trump")
        assert response.code == 302, response.body
        assert response.headers['Location'] == "/alice/"


    @mock.patch('requests.post')
    @mock.patch('requests.get')
    def test_associate_connects(self, get, post):
        self.make_participant('alice')
        self.client.website.oauth_cache = {"deadbeef": ("deadbeef", "connect", "")}

        post.return_value.status_code = 200
        post.return_value.text = "oauth_token=foo&oauth_token_secret=foo&screen_name=foo"

        get.return_value.status_code = 200
        get.return_value.text = '{"id": 1234, "screen_name": "alice"}'

        response = self.client.GxT("/on/twitter/associate?oauth_token=deadbeef&"
                                   "oauth_verifier=donald_trump", auth_as="alice")
        assert response.code == 302, response.body
        assert response.headers['Location'] == "/alice/"

        rec = self.db.one("SELECT * FROM elsewhere")
        assert rec.participant == 'alice', rec
        assert rec.platform == 'twitter', rec


    @mock.patch('requests.post')
    @mock.patch('requests.get')
    def test_associate_confirms_on_connect(self, get, post):
        TwitterAccount(self.db, '1234', {'screen_name': 'alice'}).opt_in('alice')

        self.make_participant('bob')
        self.client.website.oauth_cache = {"deadbeef": ("deadbeef", "connect", "")}

        post.return_value.status_code = 200
        post.return_value.text = "oauth_token=foo&oauth_token_secret=foo&screen_name=foo"

        get.return_value.status_code = 200
        get.return_value.text = '{"id": 1234, "screen_name": "alice"}'

        response = self.client.GxT("/on/twitter/associate?oauth_token=deadbeef&"
                                   "oauth_verifier=donald_trump", auth_as="bob")
        assert "Please Confirm" in response.body


    @mock.patch('requests.post')
    @mock.patch('requests.get')
    def test_confirmation_properly_displays_remaining_bitbucket(self, get, post):
        alice, foo = TwitterAccount(self.db, '1234', {'screen_name': 'alice'}).opt_in('alice')
        alice.participant.take_over(BitbucketAccount(self.db, '1234', {'username': 'alice_bb'}))

        self.make_participant('bob')
        self.client.website.oauth_cache = {"deadbeef": ("deadbeef", "connect", "")}

        post.return_value.status_code = 200
        post.return_value.text = "oauth_token=foo&oauth_token_secret=foo&screen_name=foo"

        get.return_value.status_code = 200
        get.return_value.text = '{"id": 1234, "screen_name": "alice"}'

        response = self.client.GxT("/on/twitter/associate?oauth_token=deadbeef&"
                                   "oauth_verifier=donald_trump", auth_as="bob")
        assert response.body.count("alice_bb<br />") == 2


    def test_can_post_to_take_over(self):
        TwitterAccount(self.db, '1234', {'screen_name': 'alice'}).opt_in('alice')

        self.make_participant('bob')
        self.client.website.connect_tokens = {("bob", "twitter", "1234"): "deadbeef"}

        response = self.client.PxST( "/on/take-over.html"
                                   , data={ "platform": "twitter"
                                          , "user_id": "1234"
                                          , "connect_token": "deadbeef"
                                          , "should_reconnect": "yes"
                                           }
                                   , auth_as="bob"
                                    )

        assert response.code == 302, response.body
        expected = '/about/me.html'
        actual = response.headers['Location']
        assert actual == expected
