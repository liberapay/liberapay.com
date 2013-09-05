from __future__ import print_function, unicode_literals

from aspen.website import Website
from gittip.elsewhere.twitter import TwitterAccount
from gittip.testing import Harness
from gittip.elsewhere import bitbucket, github, twitter

# I ended up using TwitterAccount to test even though this is generic
# functionality, because the base class is too abstract.


class TestAccountElsewhere(Harness):

    def test_opt_in_can_change_username(self):
        account = TwitterAccount("alice", {})
        expected = "bob"
        actual = account.opt_in("bob")[0].participant.username
        assert actual == expected, actual

    def test_opt_in_doesnt_have_to_change_username(self):
        self.make_participant("bob")
        account = TwitterAccount("alice", {})
        expected = account.participant # A random one.
        actual = account.opt_in("bob")[0].participant.username
        assert actual == expected, actual


    # https://github.com/gittip/www.gittip.com/issues/1042
    # ====================================================

    xss = '/on/twitter/"><img src=x onerror=prompt(1);>/'
    def test_twitter_oauth_url_percent_encodes_then(self):
        expected = '/on/twitter/redirect?action=opt-in&then=L29uL3R3aXR0ZXIvIj48aW1nIHNyYz14IG9uZXJyb3I9cHJvbXB0KDEpOz4v'
        actual = twitter.oauth_url( website=None
                                  , action='opt-in'
                                  , then=self.xss
                                   )
        assert actual == expected, actual

    def test_bitbucket_oauth_url_percent_encodes_then(self):
        expected = '/on/bitbucket/redirect?action=opt-in&then=L29uL3R3aXR0ZXIvIj48aW1nIHNyYz14IG9uZXJyb3I9cHJvbXB0KDEpOz4v'
        actual = bitbucket.oauth_url( website=None
                                    , action='opt-in'
                                    , then=self.xss
                                     )
        assert actual == expected, actual

    def test_github_oauth_url_not_susceptible_to_injection_attack(self):
        expected = 'https://github.com/login/oauth/authorize?client_id=cheese&redirect_uri=nuts?data=b3B0LWluLC9vbi90d2l0dGVyLyI+PGltZyBzcmM9eCBvbmVycm9yPXByb21wdCgxKTs+Lw=='
        website = Website([])
        website.github_client_id = 'cheese'
        website.github_callback= 'nuts'
        actual = github.oauth_url( website=website
                                 , action='opt-in'
                                 , then=self.xss
                                  )
        assert actual == expected, actual
