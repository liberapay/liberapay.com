from __future__ import print_function, unicode_literals

from aspen import json
from gratipay.testing import Harness
from gratipay.models.participant import Participant


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

    def test_participant_does_show_up_on_search(self):
        assert 'alice' in self.client.GET("/search?q=alice").body

    def test_participant_doesnt_show_up_on_search(self):
        self.hit_privacy('POST', data={'toggle': 'is_searchable'})
        assert 'alice' not in self.client.GET("/search?q=alice").body

    def test_team_participant_does_show_up_on_explore_teams(self):
        alice = Participant.from_username('alice')
        self.make_participant('A-Team', number='plural').add_member(alice)
        assert 'A-Team' in self.client.GET("/explore/teams/").body

    def test_team_participant_doesnt_show_up_on_explore_teams(self):
        alice = Participant.from_username('alice')
        self.make_participant('A-Team', number='plural', is_searchable=False).add_member(alice)
        assert 'A-Team' not in self.client.GET("/explore/teams/").body
