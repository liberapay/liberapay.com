from gittip.testing import tip_graph
from gittip.elsewhere import twitter


def test_twitter_resolve_resolves():
    with tip_graph(('alice', 'bob', 1, True, False, False, "twitter", "2345")):
        expected = 'alice'
        actual = twitter.resolve(u'alice')
        assert actual == expected, actual
