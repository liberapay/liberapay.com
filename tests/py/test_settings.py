from liberapay.constants import PROFILE_VISIBILITY_FIELDS, PROFILE_VISIBILITY_FIELDS_S
from liberapay.testing import Harness
from liberapay.models.participant import Participant


ALL_OFF = {'visibility': PROFILE_VISIBILITY_FIELDS_S}
ALL_ON = dict({k: 'on' for k in PROFILE_VISIBILITY_FIELDS}, **ALL_OFF)


class TestPrivacy(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant('alice')

    def hit_edit(self, expected_code=302, **kw):
        response = self.client.PxST("/alice/edit/visibility", auth_as=self.alice, **kw)
        if response.code != expected_code:
            print(response.text)
        return response

    # Related to is-searchable

    def test_meta_robots_tag_added_on_opt_out(self):
        self.hit_edit(data=dict(ALL_OFF, profile_noindex='on'))
        expected = '<meta name="robots" content="noindex,nofollow" />'
        assert expected in self.client.GET("/alice/").text

    def test_team_participant_does_show_up_on_explore_teams(self):
        alice = Participant.from_username('alice')
        self.make_participant('A-Team', kind='group').add_member(alice)
        assert 'A-Team' in self.client.GET("/explore/teams/").text

    def test_team_participant_doesnt_show_up_on_explore_teams(self):
        alice = Participant.from_username('alice')
        self.make_participant('A-Team', kind='group', hide_from_lists=1).add_member(alice)
        assert 'A-Team' not in self.client.GET("/explore/teams/").text


class TestVisibility(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant('alice')

    def hit_edit(self, expected_code=302, **kw):
        response = self.client.PxST("/alice/edit/visibility", auth_as=self.alice, **kw)
        if response.code != expected_code:
            print(response.text)
        return response

    def test_participant_can_modify_visibility_settings(self):
        # turn them all on
        self.hit_edit(data=ALL_ON)
        alice = Participant.from_id(self.alice.id)
        for k in PROFILE_VISIBILITY_FIELDS:
            assert getattr(alice, k) in (1, 3, True)

        # turn them all off
        self.hit_edit(data=ALL_OFF)
        alice = Participant.from_id(self.alice.id)
        for k in PROFILE_VISIBILITY_FIELDS:
            assert getattr(alice, k) in (0, 2, False)

    def test_unsettling_participant_blurred(self):
        self.make_participant('bob', is_unsettling=1)
        bob_search_result = self.client.GET("/search?q=bob").text
        assert '<div class="mini-user mini-user-blur">' in bob_search_result

    def test_participant_view_unsettling_prompt(self):
        self.make_participant('bob', is_unsettling=1)
        view_unsettling_prompt = """This page is marked as containing potentially upsetting or embarrassing content. \
                                    Viewing it is unrecommended if you are a minor. \
                                    Would you still like to view it?""".replace("  ", "")
        bobs_page = self.client.GET("/bob/").text
        assert view_unsettling_prompt in bobs_page


class TestUsername(Harness):

    def test_participant_can_set_username(self):
        alice = self.make_participant(None)
        r = self.client.POST(
            f'/~{alice.id}/edit/username', {'username': 'alice'},
            auth_as=alice, raise_immediately=False
        )
        assert r.code == 302
        assert r.headers[b'Location'].startswith(b'/alice/edit/username')
        alice = alice.refetch()
        assert alice.username == 'alice'

    def change_username(self, new_username, auth_as='alice'):
        if auth_as:
            auth_as = self.make_participant(auth_as)

        r = self.client.POST(
            '/alice/edit/username',
            {'username': new_username, 'confirmed': 'true'},
            auth_as=auth_as, raise_immediately=False,
        )
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

    def test_forbidden_suffix(self):
        username = "keybase.txt"
        r = self.change_username(username)
        assert r.code == 400
        expected = "The username &#39;%s&#39; ends with the forbidden suffix &#39;.txt&#39;." % username
        assert expected in r.text, r.text

    def test_change_team_name(self):
        team = self.make_participant(None, kind='group')
        team.change_username('team')
        alice = self.make_participant('alice')
        team.add_member(alice)
        bob = self.make_participant('bob')
        team.add_member(bob)
        r = self.client.POST('/team/edit/username', {'username': 'Team'},
                             auth_as=alice, raise_immediately=False)
        assert r.code == 200
        assert ">Confirm</button>" in r.text
        r = self.client.POST('/team/edit/username', {'username': 'Team', 'confirmed': 'true'},
                             auth_as=alice, raise_immediately=False)
        assert r.code == 302
        assert r.headers[b'Location'].startswith(b'/Team/edit/username')
        team = team.refetch()
        assert team.username == 'Team'
        alice = alice.refetch()
        assert alice.pending_notifs == 0
        bob = bob.refetch()
        assert bob.pending_notifs == 1
