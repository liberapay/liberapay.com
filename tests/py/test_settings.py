# coding: utf8
from __future__ import print_function, unicode_literals

from liberapay.constants import PRIVACY_FIELDS, PRIVACY_FIELDS_S
from liberapay.testing import Harness
from liberapay.models.participant import Participant


ALL_OFF = {'privacy': PRIVACY_FIELDS_S}
ALL_ON = dict({k: 'on' for k in PRIVACY_FIELDS}, **ALL_OFF)


class TestPrivacy(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant('alice')

    def hit_edit(self, expected_code=302, **kw):
        response = self.client.PxST("/alice/settings/edit", auth_as=self.alice, **kw)
        if response.code != expected_code:
            print(response.text)
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
        assert expected in self.client.GET("/alice/").text

    def test_team_participant_does_show_up_on_explore_teams(self):
        alice = Participant.from_username('alice')
        self.make_participant('A-Team', kind='group').add_member(alice)
        assert 'A-Team' in self.client.GET("/explore/teams/").text

    def test_team_participant_doesnt_show_up_on_explore_teams(self):
        alice = Participant.from_username('alice')
        self.make_participant('A-Team', kind='group', hide_from_search=True).add_member(alice)
        assert 'A-Team' not in self.client.GET("/explore/teams/").text


class TestUsername(Harness):

    def change_username(self, new_username, auth_as='alice'):
        if auth_as:
            auth_as = self.make_participant(auth_as)

        r = self.client.POST('/alice/settings/edit', {'username': new_username},
                             auth_as=auth_as, raise_immediately=False)
        return r

    def test_participant_can_change_their_username(self):
        r = self.change_username("bob")
        assert r.code == 302

    def test_anonymous_gets_403(self):
        r = self.change_username("bob", auth_as=None)
        assert r.code == 403

    def test_empty(self):
        r = self.change_username('      ')
        assert r.code == 400
        assert "You need to provide a username!" in r.text, r.text

    def test_invalid(self):
        r = self.change_username("§".encode('utf8'))
        assert r.code == 400
        assert "The username &#39;§&#39; contains invalid characters." in r.text, r.text

    def test_restricted_username(self):
        r = self.change_username("assets")
        assert r.code == 400
        assert "The username &#39;assets&#39; is restricted." in r.text, r.text

    def test_unavailable(self):
        self.make_participant("bob")
        r = self.change_username("bob")
        assert r.code == 400
        assert "The username &#39;bob&#39; is already taken." in r.text, r.text

    def test_too_long(self):
        username = "I am way too long, and you know it, and the American people know it."
        r = self.change_username(username)
        assert r.code == 400
        assert "The username &#39;%s&#39; is too long." % username in r.text, r.text
