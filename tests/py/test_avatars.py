from unittest.mock import patch

from liberapay.testing import Harness
from liberapay.website import website


class TestAvatars(Harness):

    def test_update_avatar(self):
        libravatar = 'https://seccdn.libravatar.org/avatar/45da67db8d78a92d35f0f5f194328b94?'
        twitter_avatar = 'https://fake.twitter.com/path/to/avatar.jpg'
        alice = self.make_participant('alice', email='alice@example.net')
        alice.update_avatar()
        assert alice.avatar_src is None
        assert alice.avatar_url.startswith(libravatar)
        # connect a twitter account, avatar shouldn't change
        elsewhere = self.make_elsewhere('twitter', '1', 'alice', avatar_url=twitter_avatar)
        alice.take_over(elsewhere)
        assert alice.avatar_src is None
        assert alice.avatar_url.startswith(libravatar)
        # switch to twitter avatar
        alice.update_avatar('twitter:')
        assert alice.avatar_src == 'twitter:'
        assert alice.avatar_url.startswith(twitter_avatar)
        # check that a new call to update_avatar doesn't override avatar_src
        alice.update_avatar()
        assert alice.avatar_src == 'twitter:'
        assert alice.avatar_url.startswith(twitter_avatar)

    @patch.object(website.app_conf, 'check_avatar_urls', True)
    def test_check_avatar_urls(self):
        libravatar = 'https://seccdn.libravatar.org/avatar/20f0944fefc09a31e43c55bc30c25cdf?'
        alice = self.make_participant('alice', email='support@liberapay.com')
        alice.update_avatar()
        assert alice.avatar_src is None
        assert alice.avatar_url.startswith(libravatar)
        # connect a twitter account with a fake avatar URL
        fake_avatar = 'https://liberapay.com/assets/nonexistent.jpg'
        elsewhere = self.make_elsewhere('twitter', '1', 'alice', avatar_url=fake_avatar)
        alice.take_over(elsewhere)
        assert alice.avatar_src is None
        assert alice.avatar_url.startswith(libravatar)
        # attempt to switch to twitter avatar, the fake avatar URL should not be chosen
        alice.update_avatar('twitter:')
        assert alice.avatar_src == 'twitter:'
        assert alice.avatar_url.startswith(libravatar)
