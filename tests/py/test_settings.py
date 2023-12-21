from liberapay.constants import PRIVACY_FIELDS, PRIVACY_FIELDS_S
from liberapay.exceptions import AccountIsPasswordless
from liberapay.testing import EUR, Harness
from liberapay.models.participant import Participant


ALL_OFF = {'privacy': PRIVACY_FIELDS_S}
ALL_ON = dict({k: 'on' for k in PRIVACY_FIELDS}, **ALL_OFF)


class TestPrivacy(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant('alice')

    def hit_edit(self, expected_code=302, **kw):
        response = self.client.PxST("/alice/edit/privacy", auth_as=self.alice, **kw)
        if response.code != expected_code:
            print(response.text)
        return response

    def test_participant_can_modify_privacy_settings(self):
        # turn them all on
        self.hit_edit(data=ALL_ON)
        alice = Participant.from_id(self.alice.id)
        for k in PRIVACY_FIELDS:
            assert getattr(alice, k) in (1, 3, True)

        # turn them all off
        self.hit_edit(data=ALL_OFF)
        alice = Participant.from_id(self.alice.id)
        for k in PRIVACY_FIELDS:
            assert getattr(alice, k) in (0, 2, False)

    # Related to is-searchable

    def test_meta_robots_tag_added_on_opt_out(self):
        self.hit_edit(data=dict(ALL_OFF, profile_noindex='on'))
        expected = '<meta name="robots" content="noindex,nofollow" />'
        assert expected in self.client.GET("/alice/").text

    def test_explore_teams(self):
        # Create a team
        self.add_payment_account(self.alice, 'stripe')
        team = self.make_participant('A-Team', kind='group')
        team.add_member(self.alice)
        # Check that it doesn't show up in /explore/teams because it doesn't have patrons
        r = self.client.GET("/explore/teams/")
        assert 'A-Team' not in r.text
        # Add a patron
        bob = self.make_participant('bob')
        bob.set_tip_to(team, EUR('1.00'))
        bob_card = self.upsert_route(bob, 'stripe-card')
        self.make_payin_and_transfer(bob_card, team, EUR('52.00'))
        # Check that it now appears in /explore/teams
        r = self.client.GET("/explore/teams/")
        assert 'A-Team' in r.text
        # Hide the team from lists
        self.client.PxST(
            "/A-Team/edit/privacy", auth_as=self.alice,
            data={"privacy": "hide_from_lists", "hide_from_lists": "on"},
        )
        # Check that it no longer appears in /explore/teams
        r = self.client.GET("/explore/teams/")
        assert 'A-Team' not in r.text


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


class TestPassword(Harness):

    def test_setting_then_changing_then_unsetting_password(self):
        alice = self.make_participant('alice')
        form_data = {
            'new-password': 'password',
            'ignore_warning': 'true',
        }
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text

        form_data['cur-password'] = form_data['new-password']
        password = form_data['new-password'] = 'correct horse battery staple'
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text
        assert alice.authenticate_with_password(alice.id, password, context='test')
        form_data['cur-password'] = ''
        form_data['new-password'] = 'password'
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text
        assert r.headers[b"Location"] == b'/alice/settings/?password_mismatch=1'
        assert alice.authenticate_with_password(alice.id, password, context='test')

        form_data = {'action': 'unset'}
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text
        assert r.headers[b"Location"] == b'/alice/settings/?password_mismatch=1'
        assert alice.authenticate_with_password(alice.id, password, context='test')
        form_data['cur-password'] = password
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text
        assert not alice.has_password
        with self.assertRaises(AccountIsPasswordless):
            alice.authenticate_with_password(alice.id, password, context='test')


class TestRecipientSettings(Harness):

    def test_enabling_and_disabling_non_secret_donations(self):
        alice = self.make_participant('alice')
        assert alice.recipient_settings.patron_visibilities is None
        # Check that the donation form isn't proposing the visibility options
        r = self.client.GET('/alice/donate')
        assert r.code == 200
        assert 'name="visibility"' in r.text
        assert 'Secret donation' not in r.text
        assert 'Private donation' not in r.text
        assert 'Public donation' not in r.text
        # Enable non-secret donations
        r = self.client.PxST('/alice/patrons/', {'see_patrons': 'yes'}, auth_as=alice)
        assert r.code == 302
        del alice.recipient_settings
        assert alice.recipient_settings.patron_visibilities == 7
        r = self.client.GET('/alice/donate')
        assert r.code == 200
        assert 'name="visibility"' in r.text
        assert 'Secret donation' in r.text
        assert 'Private donation' in r.text
        assert 'Public donation' in r.text
        # Disable non-secret donations
        r = self.client.PxST('/alice/patrons/', {'see_patrons': 'no'}, auth_as=alice)
        assert r.code == 302
        del alice.recipient_settings
        assert alice.recipient_settings.patron_visibilities == 1
        r = self.client.GET('/alice/donate')
        assert r.code == 200
        assert 'name="visibility"' in r.text
        assert 'Secret donation' not in r.text
        assert 'Private donation' not in r.text
        assert 'Public donation' not in r.text
