from __future__ import print_function, unicode_literals

from aspen import json
from gratipay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.make_participant('alice')

    def hit_privacy(self, method='GET', expected_code=200, **kw):
        response = self.client.hit(method, "/alice/privacy.json", auth_as='alice', **kw)
        if response.code != expected_code:
            print(response.body)
        return response

    def test_participant_can_get_their_privacy_settings(self):
        response = self.hit_privacy('GET')
        actual = json.loads(response.body)
        assert actual == {'search_opt_out': False}

    def test_participant_can_toggle_search_opt_out(self):
        response = self.hit_privacy('POST', data={'toggle': 'search_opt_out'})
        actual = json.loads(response.body)
        assert actual['search_opt_out'] is True

    def test_participant_can_toggle_search_opt_out_back(self):
        response = self.hit_privacy('POST', data={'toggle': 'search_opt_out'})
        response = self.hit_privacy('POST', data={'toggle': 'search_opt_out'})
        actual = json.loads(response.body)
        assert actual['search_opt_out'] is False

    def test_meta_robots_tag_added_on_opt_out(self):
        apiResponse = self.hit_privacy('POST', data={'toggle': 'search_opt_out'})

        expected = '<meta name="robots" content="noindex,nofollow" />'
        response = self.client.GET("/alice")

        assert expected in response.body
