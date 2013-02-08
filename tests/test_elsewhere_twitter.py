from gittip.elsewhere import twitter
from gittip.models import Elsewhere
from gittip.testing import Harness


class TestElsewhereTwitter(Harness):
    def test_twitter_resolve_resolves(self):
        alice = self.make_participant('alice')
        alice_on_twitter = Elsewhere(platform='twitter', user_id="1",
                                     user_info={'screen_name': 'alice'})
        alice.accounts_elsewhere.append(alice_on_twitter)
        self.session.commit()

        expected = 'alice'
        actual = twitter.resolve(u'alice')
        assert actual == expected, actual
