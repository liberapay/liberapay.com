from __future__ import print_function, unicode_literals

from aspen import json
from gratipay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.make_participant('alice', claimed_time='now')

    def hit_privacy(self, method='GET', expected_code=200, **kw):
        response = self.client.hit(method, "/alice/privacy.json", auth_as='alice', **kw)
        if response.code != expected_code:
            print(response.body)
        return response

    def test_participant_can_get_their_privacy_settings(self):
        response = self.hit_privacy('GET')
        actual = json.loads(response.body)
        assert actual == {'is_searchable': True}

    def test_participant_can_toggle_is_searchable(self):
        response = self.hit_privacy('POST', data={'toggle': 'is_searchable'})
        actual = json.loads(response.body)
        assert actual['is_searchable'] is False

    def test_participant_can_toggle_is_searchable_back(self):
        response = self.hit_privacy('POST', data={'toggle': 'is_searchable'})
        response = self.hit_privacy('POST', data={'toggle': 'is_searchable'})
        actual = json.loads(response.body)
        assert actual['is_searchable'] is True

    def test_meta_robots_tag_added_on_opt_out(self):
        self.hit_privacy('POST', data={'toggle': 'is_searchable'})
        expected = '<meta name="robots" content="noindex,nofollow" />'
        assert expected in self.client.GET("/alice/").body
