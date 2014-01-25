from __future__ import print_function, unicode_literals

import mock
from gittip.testing import Harness



class TestElsewhereTwitter(Harness):

    @mock.patch('gittip.elsewhere.twitter.Twitter.get_user_info')
    def test_can_load_account_elsewhere_from_twitter(self, get_user_info):
        get_user_info.return_value = {"id": "123", "screen_name": "alice"}
        alice_on_twitter = self.platforms.twitter.get_account('alice')
        assert alice_on_twitter.user_id == "123"


    @mock.patch('gittip.elsewhere.twitter.Twitter.get_user_info')
    def test_account_elsewhere_has_participant_object_on_it(self, get_user_info):
        get_user_info.return_value = {"id": "123", "screen_name": "alice"}
        alice_on_twitter = self.platforms.twitter.get_account('alice')
        assert not alice_on_twitter.participant.is_claimed


    @mock.patch('gittip.elsewhere.twitter.Twitter.get_user_info')
    def test_account_elsewhere_is_twitter_account_elsewhere(self, get_user_info):
        get_user_info.return_value = {"id": "123", "screen_name": "alice"}
        alice_on_twitter = self.platforms.twitter.get_account('alice')
        assert alice_on_twitter.__class__.__name__ == 'TwitterAccount'

    @mock.patch('gittip.elsewhere.twitter.Twitter.get_user_info')
    def test_get_user_info_gets_user_info(self, get_user_info):
        self.make_elsewhere('twitter', "1", {'screen_name': 'alice'}).opt_in('alice')
        expected = {"screen_name": "alice"}
        actual = get_user_info('alice')
        assert actual == expected
