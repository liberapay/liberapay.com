from __future__ import print_function, unicode_literals

from gittip.elsewhere import twitter
from gittip.testing import Harness


class TestElsewhereTwitter(Harness):

    def test_twitter_resolve_resolves(self):
        alice_on_twitter = twitter.TwitterAccount( "1"
                                                 , {'screen_name': 'alice'}
                                                  )
        alice_on_twitter.opt_in('alice')

        expected = 'alice'
        actual = twitter.resolve(u'alice')
        assert actual == expected, actual


    def test_get_user_info_gets_user_info(self):
        twitter.TwitterAccount("1", {'screen_name': 'alice'}).opt_in('alice')
        expected = {"screen_name": "alice"}
        actual = twitter.get_user_info('alice')
        assert actual == expected, actual
