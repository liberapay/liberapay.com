from gittip.testing import (
    serve_request, tip_graph, load, GITHUB_USER_UNREGISTERED_LGTEST)

from mock import patch


def test_homepage():
    actual = serve_request('/').body
    expected = "Gittip happens every Thursday."
    assert expected in actual, actual

def test_profile():
    with tip_graph(("cheese", "puffs", 0)):
        expected = "I&rsquo;m grateful for tips"
        actual = serve_request('/cheese/').body
        assert expected in actual, actual

def test_widget():
    with tip_graph(("cheese", "puffs", 0)):
        expected = "javascript: window.open"
        actual = serve_request('/cheese/widget.html').body
        assert expected in actual, actual

def test_bank_account():
    expected = "add or change your bank account"
    actual = serve_request('/bank-account.html').body
    assert expected in actual, actual

def test_credit_card():
    expected = "add or change your credit card"
    actual = serve_request('/credit-card.html').body
    assert expected in actual, actual

def test_github_associate():
    expected = "Bad request, program!"
    actual = serve_request('/on/github/associate').body
    assert expected in actual, actual

def test_twitter_associate():
    expected = "Bad request, program!"
    actual = serve_request('/on/twitter/associate').body
    assert expected in actual, actual

def test_about():
    expected = "small weekly cash gifts"
    actual = serve_request('/about/').body
    assert expected in actual, actual

def test_about_stats():
    expected = "have joined Gittip"
    actual = serve_request('/about/stats.html').body
    assert expected in actual, actual

def test_about_charts():
    expected = "growth since it launched"
    actual = serve_request('/about/charts.html').body
    assert expected in actual, actual


@patch('gittip.elsewhere.github.requests')
def test_github_proxy(requests):
    requests.get().status_code = 200
    requests.get().text = GITHUB_USER_UNREGISTERED_LGTEST
    with load():
        expected = "<b>lgtest</b> has not joined"
        actual = serve_request('/on/github/lgtest/').body
        assert expected in actual, actual


# This hits the network. XXX add a knob to skip this
def test_twitter_proxy():
    with load():
        expected = "<b>Twitter</b> has not joined"
        actual = serve_request('/on/twitter/twitter/').body
        assert expected in actual, actual
