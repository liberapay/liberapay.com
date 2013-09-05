from __future__ import print_function, unicode_literals

from mock import patch
from nose.tools import assert_equal

from gittip.elsewhere import github
from gittip.testing import Harness, DUMMY_GITHUB_JSON
from gittip.testing.client import TestClient


class TestElsewhereGithub(Harness):

    def test_github_resolve_resolves_correctly(self):
        alice_on_github = github.GitHubAccount("1", {'login': 'alice'})
        alice_on_github.opt_in('alice')

        expected = 'alice'
        actual = github.resolve(u'alice')
        assert actual == expected, actual

    @patch('gittip.elsewhere.github.requests')
    def test_github_user_info_status_handling(self, requests):
        client = TestClient()
        # Check that different possible github statuses are handled correctly
        for (github_status, github_content), expected_gittip_response in [
                ((200, DUMMY_GITHUB_JSON), 200),
                ((404, ""), 404),
                ((500, ""), 502),
                ((777, ""), 502)]:

            requests.get().status_code = github_status
            requests.get().text = github_content
            response = client.get('/on/github/not-in-the-db/')
            assert_equal(response.code, expected_gittip_response)


    def test_get_user_info_gets_user_info(self):
        github.GitHubAccount("1", {'login': 'alice'}).opt_in('alice')
        expected = {"login": "alice"}
        actual = github.get_user_info('alice')
        assert actual == expected, actual
