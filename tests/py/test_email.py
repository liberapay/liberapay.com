from datetime import timedelta
import json
from unittest.mock import MagicMock, patch

from liberapay.exceptions import (
    BadEmailAddress, CannotRemovePrimaryEmail,
    EmailAddressIsBlacklisted, EmailAlreadyTaken,
    EmailDomainIsBlacklisted, EmailDomainUnresolvable, EmailNotVerified,
    InvalidEmailDomain, NonEmailDomain,
    TooManyEmailAddresses, TooManyEmailVerifications,
)
from liberapay.models.participant import Participant
from liberapay.security.authentication import ANON, SESSION
from liberapay.security.csrf import CSRF_TOKEN
from liberapay.testing import Harness, postgres_readonly
from liberapay.testing.emails import EmailHarness
from liberapay.utils.emails import EmailVerificationResult, check_email_blacklist


class TestEmail(EmailHarness):

    def setUp(self):
        EmailHarness.setUp(self)
        self.alice = self.make_participant('alice', email=None)

    def hit_email_spt(self, action, address, auth_as='alice', expected_code=200):
        data = {action: address}
        headers = {'HTTP_ACCEPT_LANGUAGE': 'en', 'HTTP_ACCEPT': 'application/json'}
        auth_as = self.alice if auth_as == 'alice' else auth_as
        r = self.client.POST(
            '/alice/emails/', data,
            auth_as=auth_as, raise_immediately=False,
            **headers
        )
        assert r.code == expected_code, r.text
        return r

    def get_address_id(self, addr):
        return self.db.one("""
            SELECT id
              FROM emails
             WHERE address = %s
          ORDER BY id DESC
             LIMIT 1
        """, (addr,))

    def hit_verify(self, email, nonce):
        addr_id = self.get_address_id(email) or ''
        url = '/~1/emails/verify.html?email=%s&nonce=%s' % (addr_id, nonce)
        return self.client.GET(url, raise_immediately=False)

    def verify_email(self, email):
        nonce = self.alice.get_email(email).nonce
        r = self.hit_verify(email, nonce)
        assert r.code == 200
        assert "Your email address is now verified." in r.text

    def add_and_verify_email(self, email):
        self.hit_email_spt('add-email', email)
        self.verify_email(email)
        email = self.alice.get_email(email)
        assert email.verified

    def test_participant_can_add_email(self):
        response = self.hit_email_spt('add-email', 'alice@example.com')
        msg = json.loads(response.body)['msg']
        assert msg == "A verification email has been sent to alice@example.com."
        with patch.object(self.website.app_conf, 'check_email_domains', True):
            email = self.website.env.test_email_address
            response = self.hit_email_spt('add-email', email)
            msg = json.loads(response.body)['msg']
            assert msg == f"A verification email has been sent to {email}."

    def test_participant_can_add_email_with_unicode_domain_name(self):
        punycode_email = 'alice@' + 'accentué.com'.encode('idna').decode()
        self.hit_email_spt('add-email', 'alice@accentué.com')
        assert self.alice.get_email_address() == punycode_email

    def test_participant_cannot_add_email_with_unicode_local_part(self):
        self.hit_email_spt('add-email', 'tête@exemple.fr', expected_code=400)

    def test_participant_cant_add_bad_email(self):
        bad = (
            'a\nb@example.net',
            'alice@ex\rample.com',
            '\0bob@example.org',
            'x' * 309 + '@example.com',
        )
        for blob in bad:
            with self.assertRaises(BadEmailAddress):
                self.client.POST(
                    '/alice/emails/', {'add-email': blob},
                    auth_as=self.alice,
                )

    def test_participant_cant_add_email_with_bad_domain(self):
        bad = (
            ('alice@invalid\uffffdomain.com', InvalidEmailDomain),
            ('alice@phantom.liberapay.com', EmailDomainUnresolvable),  # no MX, A or AAAA record
            ('alice@nonexistent.oy.lc', EmailDomainUnresolvable),  # NXDOMAIN
            ('alice@nullmx.liberapay.com', NonEmailDomain),  # null MX record, per RFC 7505
        )
        with patch.object(self.website.app_conf, 'check_email_domains', True):
            for email, expected_exception in bad:
                with self.assertRaises(expected_exception):
                    self.client.POST(
                        '/alice/emails/', {'add-email': email},
                        auth_as=self.alice,
                    )

    def test_verification_link_uses_address_id(self):
        address = 'alice@gratipay.com'
        self.hit_email_spt('add-email', address)
        addr_id = self.get_address_id(address)
        last_email = self.get_last_email()
        assert "/alice/emails/confirm?email.id=%s&" % addr_id in last_email['text']

    def test_adding_email_sends_verification_email(self):
        self.alice.add_email('alice@liberapay.com')
        self.mailer.reset_mock()
        self.hit_email_spt('add-email', 'alice@example.com')
        assert self.mailer.call_count == 1
        last_email = self.get_last_email()
        assert last_email['to'][0] == 'alice <alice@example.com>'
        expected = "We've received a request to associate the email address alice@example.com to "
        assert expected in last_email['text']

    def test_adding_second_email_requires_recent_password_authentication(self):
        initial_session = self.alice.session = self.alice.start_session(suffix='.in')
        self.add_and_verify_email('alice1@example.com')
        assert len(self.alice.get_emails()) == 1
        self.alice.update_password('password')
        self.db.run("""
            UPDATE user_secrets
               SET mtime = mtime - interval '30 minutes'
             WHERE participant = %s
        """, (self.alice.id,))
        data = {'add-email': 'alice2@example.com'}
        r = self.client.POST(
            '/alice/emails/', data,
            auth_as=self.alice, raise_immediately=False,
        )
        assert r.code == 200, r.text
        assert "Please input your password to confirm this action:" in r.text
        assert len(self.alice.get_emails()) == 1
        data['form.repost'] = 'true'
        data['log-in.id'] = '~' + str(self.alice.id)
        data['log-in.password'] = 'password'
        r = self.client.POST(
            '/alice/emails/', data,
            auth_as=self.alice, raise_immediately=False,
        )
        assert r.code == 302, r.text
        assert len(self.alice.get_emails()) == 2
        new_session_id, new_session_secret = r.headers.cookie[SESSION].value.split(':')[1:]
        assert int(new_session_id) == initial_session.id
        assert new_session_secret != initial_session.secret

    def test_adding_second_email_sends_verification_notice(self):
        self.add_and_verify_email('alice1@example.com')
        self.hit_email_spt('add-email', 'alice2@example.com')
        assert self.mailer.call_count == 3
        last_email = self.get_last_email()
        assert last_email['to'][0] == 'alice <alice1@example.com>'
        expected = "Someone is attempting to associate the email address alice2@example.com to "
        assert expected in last_email['text']

    def test_post_anon_returns_403(self):
        self.hit_email_spt('add-email', 'anon@example.com', auth_as=None, expected_code=403)

    def test_post_with_no_at_symbol_is_400(self):
        self.hit_email_spt('add-email', 'example.com', expected_code=400)

    def test_post_with_no_period_symbol_is_400(self):
        self.hit_email_spt('add-email', 'test@example', expected_code=400)

    def test_verify_email_without_adding_email(self):
        response = self.hit_verify('', 'sample-nonce')
        assert 'The confirmation of your email address has failed.' in response.text

    def test_verify_email_wrong_nonce(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        nonce = 'fake-nonce'
        email_row = self.alice.get_email('alice@example.com')
        r = self.alice.verify_email(email_row.id, nonce, self.alice, MagicMock())
        assert r == EmailVerificationResult.FAILED
        self.hit_verify('alice@example.com', nonce)
        expected = None
        actual = Participant.from_username('alice').email
        assert expected == actual

    def test_verify_email_wrong_participant(self):
        address = 'alice@example.com'
        self.hit_email_spt('add-email', address)
        email_row = self.alice.get_email(address)
        bob = self.make_participant('bob')
        r = bob.verify_email(email_row.id, email_row.nonce, self.alice, MagicMock())
        assert r == EmailVerificationResult.FAILED

    def test_verify_email_a_second_time_returns_redundant(self):
        address = 'alice@example.com'
        self.hit_email_spt('add-email', address)
        email_row = self.alice.get_email(address)
        r = self.alice.verify_email(email_row.id, email_row.nonce, ANON, MagicMock())
        r = self.alice.verify_email(email_row.id, email_row.nonce, ANON, MagicMock())
        assert r == EmailVerificationResult.REDUNDANT

    def test_verify_only_email_with_expired_nonce(self):
        address = 'alice@example.com'
        self.hit_email_spt('add-email', address)
        self.db.run("""
            UPDATE emails
               SET added_time = (now() - INTERVAL '25 hours')
             WHERE participant = %s
        """, (self.alice.id,))
        email_row = self.alice.get_email(address)
        r = self.alice.verify_email(email_row.id, email_row.nonce, self.alice, MagicMock())
        assert r == EmailVerificationResult.SUCCEEDED

    def test_verify_secondary_email_expired_nonce(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        self.db.run("""
            UPDATE emails
               SET added_time = (now() - INTERVAL '25 hours')
             WHERE participant = %s
        """, (self.alice.id,))
        email_row = self.alice.get_email('alice@example.com')
        self.hit_email_spt('add-email', 'alice@liberapay.com')
        r = self.alice.verify_email(email_row.id, email_row.nonce, ANON, MagicMock())
        assert r == EmailVerificationResult.LOGIN_REQUIRED
        actual = self.alice.refetch().email
        assert actual == None
        r = self.alice.verify_email(email_row.id, email_row.nonce, self.alice, MagicMock())
        assert r == EmailVerificationResult.SUCCEEDED

    def test_verify_email_doesnt_leak_whether_an_email_is_linked_to_an_account_or_not(self):
        self.alice.add_email('alice@example.com')
        email_row_alice = self.alice.get_email('alice@example.com')
        bob = self.make_participant('bob', email='bob@example.com')
        email_row_bob = bob.get_email(bob.email)
        r1 = self.alice.verify_email(email_row_alice.id, 'bad nonce', ANON, MagicMock())
        assert r1 == EmailVerificationResult.FAILED
        self.db.run("""
            UPDATE emails
               SET added_time = (now() - INTERVAL '2 years')
             WHERE participant = %s
        """, (self.alice.id,))
        r2 = self.alice.verify_email(email_row_alice.id, 'bad nonce', ANON, MagicMock())
        assert r2 == EmailVerificationResult.FAILED
        r3 = bob.verify_email(email_row_bob.id, 'bad nonce', ANON, MagicMock())
        assert r3 == EmailVerificationResult.FAILED

    def test_verify_email(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        nonce = self.alice.get_email('alice@example.com').nonce
        self.hit_verify('alice@example.com', nonce)
        alice = Participant.from_username('alice')
        assert alice.email == 'alice@example.com'
        # Add and verify a second email address a year later, the primary email
        # address should stay the same.
        self.db.run("UPDATE emails SET added_time = added_time - interval '1 year'")
        self.hit_email_spt('add-email', 'alice@example.net')
        nonce = self.alice.get_email('alice@example.net').nonce
        self.hit_verify('alice@example.net', nonce)
        alice = alice.refetch()
        assert alice.email == 'alice@example.com'

    def test_verify_email_with_unicode_domain(self):
        punycode_email = 'alice@' + 'accentué.fr'.encode('idna').decode()
        self.alice.add_email(punycode_email)
        nonce = self.alice.get_email(punycode_email).nonce
        self.hit_verify(punycode_email, nonce)
        actual = Participant.from_username('alice').email
        assert punycode_email == actual

    def test_verify_email_without_cookies(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        email = self.alice.get_email('alice@example.com')
        url = '/~1/emails/verify.html?email=%s&nonce=%s' % (email.id, email.nonce)
        r = self.client.GET(url, csrf_token=None, raise_immediately=False)
        assert r.code == 200, r.text
        refresh_url = "?email=%s&nonce=%s&cookie_sent=true" % (email.id, email.nonce)
        assert r.headers[b"Refresh"] == b"0;url=" + refresh_url.encode('ascii')
        assert CSRF_TOKEN in r.headers.cookie
        csrf_token = r.headers.cookie[CSRF_TOKEN].value
        r = self.client.GET(url, csrf_token=csrf_token, raise_immediately=False)
        assert r.code == 200, r.text
        assert b"Refresh" not in r.headers
        assert CSRF_TOKEN not in r.headers.cookie
        self.alice = self.alice.refetch()
        assert self.alice.email == email.address

    def test_verified_email_is_not_changed_after_update(self):
        self.add_and_verify_email('alice@example.com')
        self.alice.add_email('alice@example.net')
        expected = 'alice@example.com'
        actual = Participant.from_username('alice').email
        assert expected == actual

    def test_disavow_email(self):
        self.client.PxST('/sign-up', {
            'sign-in.email': 'bob@liberapay.com',
            'sign-in.username': 'bob',
            'sign-in.currency': 'USD',
        })
        bob = Participant.from_username('bob')
        email = bob.get_email('bob@liberapay.com')
        qs = '?email.id=%s&email.nonce=%s' % (email.id, email.nonce)
        url = '/bob/emails/disavow' + qs
        verification_email = self.get_last_email()
        assert url in verification_email['text']

        # Test the disavowal URL without cookies
        r = self.client.GET(url, csrf_token=None, raise_immediately=False)
        assert r.code == 200
        refresh_qs = qs + '&cookie_sent=true'
        assert r.headers[b"Refresh"] == b'0;url=' + refresh_qs.encode()
        assert CSRF_TOKEN in r.headers.cookie
        email = bob.get_email(email.address)
        assert email.disavowed is None
        assert email.disavowed_time is None
        assert email.verified is None
        assert email.verified_time is None

        # Test the disavowal URL with cookies
        r = self.client.GET(url)
        assert r.code == 200
        email = bob.get_email(email.address)
        assert email.disavowed is True
        assert email.disavowed_time is not None
        assert email.verified is None
        assert email.verified_time is None
        assert email.nonce

        # Check idempotency
        r = self.client.GET(url)
        assert r.code == 200

        # Check that resending the verification email isn't allowed
        r = self.client.POST(
            '/bob/emails/', {'resend': email.address},
            auth_as=bob, raise_immediately=False,
        )
        assert r.code == 400, r.text

        # Test adding the address to the blacklist
        r = self.client.POST(url, {'action': 'add_to_blacklist'})
        assert r.code == 200, r.text
        with self.assertRaises(EmailAddressIsBlacklisted):
            check_email_blacklist(email.address)

        # and removing it
        r = self.client.POST(url, {'action': 'remove_from_blacklist'})
        assert r.code == 200, r.text
        assert check_email_blacklist(email.address) is None

    def test_disavowal_can_be_reversed(self):
        self.client.PxST('/sign-up', {
            'sign-in.email': 'bob@liberapay.com',
            'sign-in.username': 'bob',
            'sign-in.currency': 'USD',
        })
        bob = Participant.from_username('bob')
        email = bob.get_email('bob@liberapay.com')
        qs = '?email.id=%s&email.nonce=%s' % (email.id, email.nonce)
        url = '/bob/emails/disavow' + qs

        # Disavow
        r = self.client.GET('/bob/emails/disavow' + qs)
        assert r.code == 200
        email = bob.get_email(email.address)
        assert email.disavowed is True
        assert email.disavowed_time is not None
        assert email.verified is None
        assert email.verified_time is None
        assert email.nonce

        # Add the address to the blacklist
        r = self.client.POST(url, {'action': 'add_to_blacklist'})
        assert r.code == 200, r.text
        with self.assertRaises(EmailAddressIsBlacklisted):
            check_email_blacklist(email.address)

        # Reverse the disavowal
        r = self.client.GET('/bob/emails/confirm' + qs)
        assert r.code == 200, r.text
        email = bob.get_email(email.address)
        assert email.disavowed is False
        assert email.disavowed_time is not None
        assert email.verified is True
        assert email.verified_time is not None
        assert email.nonce
        assert check_email_blacklist(email.address) is None

    def test_self_disavowal_is_not_allowed(self):
        self.client.PxST('/sign-up', {
            'sign-in.email': 'bob@liberapay.com',
            'sign-in.username': 'bob',
            'sign-in.currency': 'USD',
        })
        bob = Participant.from_username('bob')
        email = bob.get_email('bob@liberapay.com')
        qs = '?email.id=%s&email.nonce=%s' % (email.id, email.nonce)
        url = '/bob/emails/disavow' + qs
        verification_email = self.get_last_email()
        assert url in verification_email['text']
        # Check that the disavowal page redirects to the confirmation page when logged in
        r = self.client.GET(url, auth_as=bob, raise_immediately=False)
        assert r.code == 200
        assert r.headers[b"Refresh"] == b"0;url=/bob/emails/confirm" + qs.encode()
        email = bob.get_email(email.address)
        assert email.disavowed is None
        assert email.disavowed_time is None
        assert email.verified is None
        assert email.verified_time is None
        assert email.nonce
        # Check that following the redirect confirms the email address
        r = self.client.GET(r.headers[b"Refresh"][6:].decode(), auth_as=bob)
        assert r.code == 200
        email = bob.get_email(email.address)
        assert email.disavowed is not True
        assert email.disavowed_time is None
        assert email.verified is True
        assert email.verified_time is not None
        assert email.nonce

    def test_get_emails(self):
        self.add_and_verify_email('alice@example.com')
        self.alice.add_email('alice@example.net')
        emails = self.alice.get_emails()
        assert len(emails) == 2

    def test_nonce_is_reused_when_resending_email(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        nonce1 = self.alice.get_email('alice@example.com').nonce
        self.hit_email_spt('resend', 'alice@example.com')
        nonce2 = self.alice.get_email('alice@example.com').nonce
        assert nonce1 == nonce2

    def test_cannot_update_email_to_already_verified(self):
        bob = self.make_participant('bob')
        self.alice.add_email('alice@example.com')
        email_row = self.alice.get_email('alice@example.com')
        r = self.alice.verify_email(email_row.id, email_row.nonce, ANON, MagicMock())
        assert r == EmailVerificationResult.SUCCEEDED

        with self.assertRaises(EmailAlreadyTaken):
            bob.add_email('alice@example.com')
            nonce = bob.get_email('alice@example.com').nonce
            bob.hit_verify('alice@example.com', nonce)

        email_alice = Participant.from_username('alice').email
        assert email_alice == 'alice@example.com'

    def test_cannot_add_too_many_emails_per_day(self):
        self.alice.add_email('alice@example.com')
        self.alice.add_email('alice@example.net')
        self.alice.add_email('alice@example.org')
        self.alice.add_email('alice@example.co.uk')
        self.alice.add_email('alice@example.io')
        with self.assertRaises(TooManyEmailVerifications):
            self.alice.add_email('alice@example.coop')

    def test_cannot_add_too_many_emails_ever(self):
        self.alice.add_email('alice@example.com')
        self.alice.add_email('alice@example.net')
        self.alice.add_email('alice@example.org')
        self.alice.add_email('alice@example.co.uk')
        self.alice.add_email('alice@example.io')
        self.db.run("DELETE FROM rate_limiting")
        self.alice.add_email('alice@example.co')
        self.alice.add_email('alice@example.eu')
        self.alice.add_email('alice@example.asia')
        self.alice.add_email('alice@example.museum')
        self.alice.add_email('alice@example.py')
        with self.assertRaises(TooManyEmailAddresses):
            self.alice.add_email('alice@example.coop')

    def test_email_addresses_are_normalized(self):
        self.alice.add_email('\t Alice&Bob@ExAmPlE.InFo \n')
        assert self.alice.get_email_address() == 'Alice&Bob@example.info'

    def test_emails_page_shows_emails(self):
        self.add_and_verify_email('alice@example.com')
        self.alice.add_email('alice@example.net')
        body = self.client.GET("/alice/emails/", auth_as=self.alice).text
        assert 'alice@example.com' in body
        assert 'alice@example.net' in body

    def test_set_primary(self):
        self.add_and_verify_email('alice@example.com')
        self.add_and_verify_email('alice@example.net')
        self.hit_email_spt('set-primary', 'alice@example.com')  # noop
        self.hit_email_spt('set-primary', 'alice@example.net')

    def test_cannot_set_primary_to_unverified(self):
        with self.assertRaises(EmailNotVerified):
            self.alice.update_email('alice@example.com')

    def test_remove_email(self):
        # Cannot remove unverified primary
        self.hit_email_spt('add-email', 'alice@example.com')
        with self.assertRaises(CannotRemovePrimaryEmail):
            self.alice.remove_email('alice@example.com')

        # Can remove extra unverified
        self.hit_email_spt('add-email', 'alice@example.org')
        self.hit_email_spt('remove', 'alice@example.org')

        # Can remove extra verified
        self.verify_email('alice@example.com')
        self.add_and_verify_email('alice@example.net')
        self.hit_email_spt('remove', 'alice@example.net')

        # Cannot remove primary
        with self.assertRaises(CannotRemovePrimaryEmail):
            self.alice.remove_email('alice@example.com')

        # Can reclaim removed verified email address
        self.add_and_verify_email('alice@example.net')

    def test_html_escaping(self):
        self.alice.add_email("foo'bar@example.com")
        last_email = self.get_last_email()
        assert 'foo&#39;bar' in last_email['html']
        assert '&#39;' not in last_email['text']

    def queue_email(self, participant, event, **context):
        return participant.notify(event, force_email=True, web=False, **context)

    def test_can_dequeue_an_email(self):
        larry = self.make_participant('larry', email='larry@example.com')
        self.queue_email(larry, 'team_invite', team='team', team_url='fake_url', inviter='bob')

        Participant.dequeue_emails()
        Participant.dequeue_emails()
        assert self.mailer.call_count == 1
        last_email = self.get_last_email()
        assert last_email['to'][0] == 'larry <larry@example.com>'
        assert self.db.one("SELECT email_status FROM notifications") == 'sent'

    def test_dequeueing_an_email_without_address_just_skips_it(self):
        larry = self.make_participant('larry')
        self.queue_email(larry, 'team_invite', team='team', team_url='fake_url', inviter='bob')

        Participant.dequeue_emails()
        assert self.mailer.call_count == 0
        assert self.db.one("SELECT email_status FROM notifications") == 'skipped'

    def test_emails_are_not_sent_went_database_is_read_only(self):
        larry = self.make_participant('larry')
        self.queue_email(larry, 'team_invite', team='team', team_url='fake_url', inviter='bob')
        with postgres_readonly(self.db):
            Participant.dequeue_emails()
            assert self.mailer.call_count == 0
            assert self.db.one("SELECT email_status FROM notifications") == 'queued'

    def test_blacklisting_email_domain(self):
        admin = self.make_participant('admin', privileges=1)
        check_email_blacklist('example@example.com')
        r = self.client.GET('/admin/email-domains?domain=example.com', auth_as=admin)
        assert r.code == 200, r.text
        r = self.client.PxST(
            '/admin/email-domains?domain=example.com',
            {'action': 'add_to_blacklist', 'reason': 'bounce'},
            auth_as=admin,
        )
        assert r.code == 302, r.text
        r = self.client.GET('/admin/email-domains?domain=example.com', auth_as=admin)
        assert r.code == 200, r.text
        with self.assertRaises(EmailDomainIsBlacklisted):
            check_email_blacklist('example@example.com')

    def test_emails_are_translated_in_whole_or_not_at_all(self):
        alice = self.alice
        alice.set_email_lang('FR')
        alice.add_email('alice@liberapay.com')
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['subject'] == "Vérification de votre adresse électronique - Liberapay"

        email_row = alice.get_email('alice@liberapay.com')
        translation = self.website.locales['fr'].catalog._messages.pop("Greetings,")
        try:
            alice.send_email(
                'login_link', email_row,
                username='alice', link_validity=timedelta(hours=6)
            )
        finally:
            self.website.locales['fr'].catalog._messages["Greetings,"] = translation
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['subject'] == "Log in to Liberapay"


class TestEmail2(Harness):

    def test_participant_with_long_email_address_can_receive_messages(self):
        email = 'a' * 200 + '@example.org'
        fred = self.make_participant(None, email=email)
        r = self.client.PxST(
            f'/~{fred.id}/identity',
            {'name': "You don't need to know my legal name"},
            auth_as=fred,
        )
        assert r.code == 302
        fred.notify('team_invite', team='team', team_url='fake_url', inviter='bob')
        Participant.dequeue_emails()
        assert self.db.one("SELECT email_status FROM notifications") == 'sent'

    def test_participant_with_long_nonascii_name_can_receive_emails(self):
        fred = self.make_participant(None, email='frederic@example.org')
        r = self.client.PxST(
            f'/~{fred.id}/identity',
            {'name': "Frédéric d'Arundel d'Esquincourt de Condé"},
            auth_as=fred,
        )
        assert r.code == 302
        fred.notify('team_invite', team='team', team_url='fake_url', inviter='bob')
        Participant.dequeue_emails()
        assert self.db.one("SELECT email_status FROM notifications") == 'sent'
