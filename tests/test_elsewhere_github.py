from gittip.testing import tip_graph, serve_request, DUMMY_GITHUB_JSON
from gittip.elsewhere import github

from mock import patch
from nose.tools import assert_equal


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
