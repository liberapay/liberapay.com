from __future__ import print_function, unicode_literals

from mock import patch

from gittip.elsewhere import github
from gittip.testing import Harness, DUMMY_GITHUB_JSON


class TestElsewhereGithub(Harness):

    @patch('gittip.elsewhere.github.requests')
    def test_github_user_info_status_handling(self, requests):
        # Check that different possible github statuses are handled correctly
        for (github_status, github_content), expected_gittip_response in [
                ((200, DUMMY_GITHUB_JSON), 200),
                ((404, ""), 404),
                ((500, ""), 502),
                ((777, ""), 502)]:

            requests.get().status_code = github_status
            requests.get().text = github_content
            method = self.client.GET if expected_gittip_response == 200 else self.client.GxT
            response = method('/on/github/not-in-the-ab/')
            assert response.code == expected_gittip_response


    def test_get_user_info_gets_user_info(self):
        github.GitHubAccount(self.db, "1", {'login': 'alice'}).opt_in('alice')
        expected = {"login": "alice"}
        actual = github.get_user_info(self.db, 'alice')
        assert actual == expected
