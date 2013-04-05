from mock import patch
from nose.tools import assert_equal

from gittip.elsewhere import github
from gittip.models import Elsewhere
from gittip.testing import Harness, DUMMY_GITHUB_JSON
from gittip.testing.client import TestClient


class TestElsewhereGithub(Harness):
    def test_github_resolve_resolves_correctly(self):
        alice = self.make_participant('alice')
        alice_on_github = Elsewhere(platform='github', user_id="1",
                                    user_info={'login': 'alice'})
        alice.accounts_elsewhere.append(alice_on_github)
        self.session.commit()

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
            print response.code, expected_gittip_response, response.body
            assert_equal(response.code, expected_gittip_response)
