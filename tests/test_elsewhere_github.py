from gittip.testing import tip_graph, serve_request
from gittip.elsewhere import github

from mock import patch
from nose.tools import assert_equal

DUMMY_GITHUB_JSON = u'{"html_url":"https://github.com/whit537","type":"User","public_repos":25,"blog":"http://whit537.org/","gravatar_id":"fb054b407a6461e417ee6b6ae084da37","public_gists":29,"following":15,"updated_at":"2013-01-14T13:43:23Z","company":"Gittip","events_url":"https://api.github.com/users/whit537/events{/privacy}","repos_url":"https://api.github.com/users/whit537/repos","gists_url":"https://api.github.com/users/whit537/gists{/gist_id}","email":"chad@zetaweb.com","organizations_url":"https://api.github.com/users/whit537/orgs","hireable":false,"received_events_url":"https://api.github.com/users/whit537/received_events","starred_url":"https://api.github.com/users/whit537/starred{/owner}{/repo}","login":"whit537","created_at":"2009-10-03T02:47:57Z","bio":"","url":"https://api.github.com/users/whit537","avatar_url":"https://secure.gravatar.com/avatar/fb054b407a6461e417ee6b6ae084da37?d=https://a248.e.akamai.net/assets.github.com%2Fimages%2Fgravatars%2Fgravatar-user-420.png","followers":90,"name":"Chad Whitacre","followers_url":"https://api.github.com/users/whit537/followers","following_url":"https://api.github.com/users/whit537/following","id":134455,"location":"Pittsburgh, PA","subscriptions_url":"https://api.github.com/users/whit537/subscriptions"}'


def test_github_resolve_resolves():
    with tip_graph(('alice', 'bob', 1)):
        expected = 'alice'
        actual = github.resolve(u'alice')
        assert actual == expected, actual


@patch('gittip.elsewhere.github.requests')
def test_github_user_info_status_handling(requests):
    # Check that different possible github statuses are handled correctly
    for (github_status, github_content), expected_gittip_response in [
            ((200, DUMMY_GITHUB_JSON), 200),
            ((404, ""), 404),
            ((500, ""), 502),
            ((777, ""), 502)]:

        requests.get().status_code = github_status
        requests.get().text = github_content
        response = serve_request('/on/github/not-in-the-db/')
        assert_equal(response.code, expected_gittip_response)
