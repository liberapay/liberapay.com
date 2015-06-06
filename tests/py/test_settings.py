from __future__ import print_function, unicode_literals

from liberapay.constants import PRIVACY_FIELDS, PRIVACY_FIELDS_S
from liberapay.testing import Harness
from liberapay.models.participant import Participant


ALL_OFF = {'privacy': PRIVACY_FIELDS_S}
ALL_ON = dict({k: 'on' for k in PRIVACY_FIELDS}, **ALL_OFF)


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant('alice')

    def hit_edit(self, expected_code=302, **kw):
        response = self.client.PxST("/alice/settings/edit", auth_as=self.alice, **kw)
        if response.code != expected_code:
            print(response.body)
        return response

    def test_participant_can_modify_privacy_settings(self):
        # turn them all on
        self.hit_edit(data=ALL_ON)
        alice = Participant.from_id(self.alice.id)
        for k in PRIVACY_FIELDS:
            assert getattr(alice, k) is True

        # turn them all off
        self.hit_edit(data=ALL_OFF)
        alice = Participant.from_id(self.alice.id)
        for k in PRIVACY_FIELDS:
            assert getattr(alice, k) is False

    # Related to is-searchable

    def test_meta_robots_tag_added_on_opt_out(self):
        self.hit_edit(data=dict(ALL_OFF, hide_from_search='on'))
        expected = '<meta name="robots" content="noindex,nofollow" />'
        assert expected in self.client.GET("/alice/").body

    def test_team_participant_does_show_up_on_explore_teams(self):
        alice = Participant.from_username('alice')
        self.make_participant('A-Team', kind='group').add_member(alice)
        assert 'A-Team' in self.client.GET("/explore/teams/").body

    def test_team_participant_doesnt_show_up_on_explore_teams(self):
        alice = Participant.from_username('alice')
        self.make_participant('A-Team', kind='group', hide_from_search=True).add_member(alice)
        assert 'A-Team' not in self.client.GET("/explore/teams/").body
