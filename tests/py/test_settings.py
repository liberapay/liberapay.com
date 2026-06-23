import json as stdlib_json
from types import SimpleNamespace
from unittest.mock import patch

from liberapay.constants import PRIVACY_FIELDS, PRIVACY_FIELDS_S
from liberapay.exceptions import AccountIsPasswordless
from liberapay.security.otp import generate_totp_code
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
            'new-password': 'a',
            'back_to': alice.path('settings/'),
        }
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 400, r.text
        form_data['new-password'] = 'password'
        r = self.client.PxST(
            '/alice/settings/edit', form_data, auth_as=alice, skip_password_check=True,
        )
        assert r.code == 302, r.text
        form_data['cur-password'] = form_data['new-password']
        form_data['new-password'] = 'a'*200
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 400, r.text

        password = form_data['new-password'] = 'correct horse battery staple'
        r = self.client.PxST(
            '/alice/settings/edit', form_data, auth_as=alice, skip_password_check=True,
        )
        assert r.code == 302, r.text
        assert alice.authenticate_with_password(alice.id, password)
        form_data['cur-password'] = ''
        form_data['new-password'] = 'password'
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text
        assert r.headers[b"Location"] == b'/alice/settings/?password_mismatch=1'
        assert alice.authenticate_with_password(alice.id, password)

        form_data = {'action': 'unset'}
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text
        assert r.headers[b"Location"] == b'/alice/settings/?password_mismatch=1'
        assert alice.authenticate_with_password(alice.id, password)
        form_data['cur-password'] = password
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text
        assert not alice.has_password
        with self.assertRaises(AccountIsPasswordless):
            alice.authenticate_with_password(alice.id, password)


class TestTwoFactorAuthentication(Harness):

    def test_enabling_and_disabling_totp(self):
        alice = self.make_participant('alice')

        r = self.client.GET('/alice/settings/', auth_as=alice)
        assert "Set up 2FA" in r.text
        assert '<svg ' in r.text
        assert "Open authenticator app" in r.text

        secret = alice.generate_totp_secret()
        code = generate_totp_code(secret)

        r = self.client.PxST('/alice/settings/edit', {
            'action': 'enable-otp',
            'otp-secret': secret,
            'otp-code': code,
            'back_to': alice.path('settings/'),
        }, auth_as=alice, skip_password_check=True)
        assert r.code == 302, r.text
        assert alice.refetch().has_totp

        r = self.client.PxST('/alice/settings/edit', {
            'action': 'disable-otp',
            'otp-code': '000000',
            'back_to': alice.path('settings/'),
        }, auth_as=alice, skip_password_check=True)
        assert r.code == 302, r.text
        assert r.headers[b"Location"] == b'/alice/settings/?otp_mismatch=1'
        assert alice.refetch().has_totp

        self.db.run("""
            UPDATE user_secrets
               SET secret = jsonb_set(secret::jsonb, '{latest_counter}', 'null'::jsonb)::text
             WHERE id = %s
        """, (Participant.TOTP_SECRET_ID,))
        r = self.client.PxST('/alice/settings/edit', {
            'action': 'disable-otp',
            'otp-code': code,
            'back_to': alice.path('settings/'),
        }, auth_as=alice, skip_password_check=True)
        assert r.code == 302, r.text
        assert not alice.refetch().has_totp

    def test_registering_and_using_a_passkey(self):
        alice = self.make_participant('alice')

        registration = alice.start_webauthn_registration()
        verified_registration = SimpleNamespace(
            credential_id=b'credential-id',
            credential_public_key=b'public-key',
            sign_count=7,
            aaguid='00000000-0000-0000-0000-000000000000',
            credential_type=SimpleNamespace(value='public-key'),
            credential_device_type=SimpleNamespace(value='single_device'),
            credential_backed_up=False,
            user_verified=True,
        )
        with patch(
            'liberapay.security.webauthn.verify_registration_response',
            return_value=verified_registration,
        ) as verify_registration:
            assert alice.enable_webauthn(
                registration['challenge_id'],
                '{"id": "credential-id"}',
                'Laptop',
            )
        verify_registration.assert_called_once()

        credentials = alice.get_webauthn_credentials()
        assert len(credentials) == 1
        assert credentials[0].name == 'Laptop'
        assert credentials[0].latest_counter == 7

        challenge = alice.start_two_factor_challenge('xyz')
        credential = stdlib_json.dumps({'id': credentials[0].credential_id})
        with patch(
            'liberapay.security.webauthn.verify_authentication_response',
            return_value=SimpleNamespace(new_sign_count=8),
        ) as verify_authentication:
            p, session_suffix = Participant.authenticate_with_two_factor_challenge(
                alice.id,
                challenge.id,
                challenge.token,
                webauthn_credential=credential,
            )
        verify_authentication.assert_called_once()
        assert p.id == alice.id
        assert session_suffix == 'xyz'
        assert p.authenticated
        assert alice.refetch().has_webauthn
        assert alice.get_webauthn_credentials()[0].latest_counter == 8

    def test_totp_secret_is_encrypted_at_rest(self):
        alice = self.make_participant('alice')
        secret = alice.generate_totp_secret()
        assert alice.enable_totp(secret, generate_totp_code(secret))
        stored = self.db.one(
            "SELECT secret FROM user_secrets WHERE participant = %s AND id = %s",
            (alice.id, Participant.TOTP_SECRET_ID)
        )
        assert secret not in stored
        assert 'fernet:' in stored
        # The secret can still be used to verify codes.
        self.db.run("""
            UPDATE user_secrets
               SET secret = jsonb_set(secret::jsonb, '{latest_counter}', 'null'::jsonb)::text
             WHERE id = %s
        """, (Participant.TOTP_SECRET_ID,))
        assert alice.check_totp(generate_totp_code(secret))

    def test_a_totp_code_cannot_be_used_twice(self):
        alice = self.make_participant('alice')
        secret = alice.generate_totp_secret()
        assert alice.enable_totp(secret, generate_totp_code(secret))
        self.db.run("""
            UPDATE user_secrets
               SET secret = jsonb_set(secret::jsonb, '{latest_counter}', 'null'::jsonb)::text
             WHERE id = %s
        """, (Participant.TOTP_SECRET_ID,))
        code = generate_totp_code(secret)
        assert alice.check_totp(code) is True
        assert alice.check_totp(code) is False

    def test_enabling_2fa_requires_the_current_password(self):
        password = 'correct-horse-battery-staple'
        alice = self.make_participant('alice', password=password)
        secret = alice.generate_totp_secret()
        code = generate_totp_code(secret)

        # Wrong password is rejected.
        r = self.client.PxST('/alice/settings/edit', {
            'action': 'enable-otp',
            'otp-secret': secret,
            'otp-code': code,
            'cur-password': 'wrong',
            'back_to': alice.path('settings/'),
        }, auth_as=alice)
        assert r.code == 302
        assert r.headers[b"Location"] == b'/alice/settings/?password_mismatch=1'
        assert not alice.refetch().has_totp

        # Correct password is accepted.
        r = self.client.PxST('/alice/settings/edit', {
            'action': 'enable-otp',
            'otp-secret': secret,
            'otp-code': code,
            'cur-password': password,
            'back_to': alice.path('settings/'),
        }, auth_as=alice)
        assert r.code == 302, r.text
        assert alice.refetch().has_totp


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
