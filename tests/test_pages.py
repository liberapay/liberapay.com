from gittip.testing import serve_request, load, setup_tips


def test_homepage():
    actual = serve_request('/').body
    expected = "Gittip happens every Thursday."
    assert expected in actual, actual

def test_profile():
    with load(*setup_tips(("cheese", "puffs", 0))):
        expected = "I&rsquo;m grateful for tips"
        actual = serve_request('/cheese/').body
        assert expected in actual, actual

def test_widget():
    with load(*setup_tips(("cheese", "puffs", 0))):
        expected = "javascript: window.open"
        actual = serve_request('/cheese/widget.html').body
        assert expected in actual, actual


# These hit the network.

def test_github_proxy():
    expected = "<b>lgtest</b> has not joined"
    actual = serve_request('/on/github/lgtest/').body
    assert expected in actual, actual

def test_twitter_proxy():
    expected = "<b>Twitter</b> has not joined"
    actual = serve_request('/on/twitter/twitter/').body
    assert expected in actual, actual
