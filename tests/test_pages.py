from gittip.testing import serve_request, tip_graph, load


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

def test_about_unclaimed():
    expected = "Unclaimed"
    actual = serve_request('/about/unclaimed.html').body
    assert expected in actual, actual

def test_public_json_nothing():
    with tip_graph(('alice', 'bob', 1)):
        expected = '{"receiving": "0.00"}'
        actual = serve_request('/alice/public.json').body
        assert expected in actual, actual

def test_public_json_something():
    with tip_graph(('alice', 'bob', 1)):
        expected = '{"receiving": "1.00"}'
        actual = serve_request('/bob/public.json').body
        assert expected in actual, actual


# These hit the network. XXX add a knob to skip these

def test_github_proxy():
    with load():
        expected = "<b>lgtest</b> has not joined"
        actual = serve_request('/on/github/lgtest/').body
        assert expected in actual, actual

def test_twitter_proxy():
    with load():
        expected = "<b>Twitter</b> has not joined"
        actual = serve_request('/on/twitter/twitter/').body
        assert expected in actual, actual
