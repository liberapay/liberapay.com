from __future__ import print_function, unicode_literals

from gittip.elsewhere import twitter
from gittip.testing import Harness


class TestElsewhereTwitter(Harness):

    def test_get_user_info_gets_user_info(self):
        twitter.TwitterAccount(self.db, "1", {'screen_name': 'alice'}).opt_in('alice')
        expected = {"screen_name": "alice"}
        actual = twitter.get_user_info(self.db, 'alice')
        assert actual == expected

    def test_get_user_info_gets_user_info_long(self):
        twitter.TwitterAccount(self.db, 2147483648, {'screen_name': 'alice'}).opt_in('alice')
        expected = {"screen_name": "alice"}
        actual = twitter.get_user_info(self.db, 'alice')
        assert actual == expected
