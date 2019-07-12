from unittest.mock import patch

from liberapay.exceptions import (
    BadEmailAddress, BadEmailDomain, CannotRemovePrimaryEmail,
    EmailAddressIsBlacklisted, EmailAlreadyTaken, EmailNotVerified,
    TooManyEmailAddresses, TooManyEmailVerifications,
)
from liberapay.models.participant import Participant
from liberapay.security.authentication import ANON
from liberapay.testing.emails import EmailHarness
from liberapay.utils.emails import EmailVerificationResult, check_email_blacklist


class TestEmail(EmailHarness):

    def setUp(self):
        EmailHarness.setUp(self)
        self.alice = self.make_participant('alice')

    def hit_email_spt(self, action, address, auth_as='alice'):
        data = {('email' if action == 'add-email' else action): address}
        headers = {'HTTP_ACCEPT_LANGUAGE': 'en', 'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        auth_as = self.alice if auth_as == 'alice' else auth_as
        return self.client.POST(
            '/alice/emails/modify.json', data,
            auth_as=auth_as, raise_immediately=False,
            **headers
        )

    def get_address_id(self, addr):
        return self.db.one("SELECT id FROM emails WHERE address = %s", (addr,))

    def hit_verify(self, email, nonce):
        addr_id = self.get_address_id(email) or ''
        url = '/alice/emails/verify.html?email=%s&nonce=%s' % (addr_id, nonce)
        return self.client.GET(url, auth_as=self.alice, raise_immediately=False)

    def verify_email(self, email):
        nonce = self.alice.get_email(email).nonce
        self.hit_verify(email, nonce)

    def add_and_verify_email(self, email):
        self.hit_email_spt('add-email', email)
        self.verify_email(email)

    def test_participant_can_add_email(self):
        response = self.hit_email_spt('add-email', 'alice@example.com')
        assert response.text == '{}'

    def test_participant_can_add_email_with_unicode_domain_name(self):
        punycode_email = 'alice@' + 'accentué.com'.encode('idna').decode()
        self.hit_email_spt('add-email', 'alice@accentué.com')
        assert self.alice.get_email_address() == punycode_email

    def test_participant_cannot_add_email_with_unicode_local_part(self):
        r = self.hit_email_spt('add-email', 'tête@exemple.fr')
        assert r.code == 400

    def test_participant_cant_add_bad_email(self):
        bad = (
            'a\nb@example.net',
            'alice@ex\rample.com',
            '\0bob@example.org',
            'x' * 309 + '@example.com',
        )
        for blob in bad:
            with self.assertRaises(BadEmailAddress):
                self.alice.add_email(blob)
            response = self.hit_email_spt('add-email', blob)
            assert response.code == 400

    def test_participant_cant_add_email_with_bad_domain(self):
        bad = (
            'alice@example.net',  # no MX record
            'alice@nonexistent.liberapay.com',  # NXDOMAIN
        )
        with patch.object(self.website, 'app_conf') as app_conf:
            app_conf.check_email_domains = True
            for email in bad:
                with self.assertRaises(BadEmailDomain):
                    self.alice.add_email(email)
                response = self.hit_email_spt('add-email', email)
                assert response.code == 400

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

    def test_adding_second_email_sends_verification_notice(self):
        self.add_and_verify_email('alice1@example.com')
        self.hit_email_spt('add-email', 'alice2@example.com')
        assert self.mailer.call_count == 3
        last_email = self.get_last_email()
        assert last_email['to'][0] == 'alice <alice1@example.com>'
        expected = "We are connecting alice2@example.com to the alice account on Liberapay"
        assert expected in last_email['text']

    def test_post_anon_returns_403(self):
        response = self.hit_email_spt('add-email', 'anon@example.com', auth_as=None)
        assert response.code == 403

    def test_post_with_no_at_symbol_is_400(self):
        response = self.hit_email_spt('add-email', 'example.com')
        assert response.code == 400

    def test_post_with_no_period_symbol_is_400(self):
        response = self.hit_email_spt('add-email', 'test@example')
        assert response.code == 400

    def test_verify_email_without_adding_email(self):
        response = self.hit_verify('', 'sample-nonce')
        assert '<h3>Failure</h3>' in response.text

    def test_verify_email_wrong_nonce(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        nonce = 'fake-nonce'
        email_row = self.alice.get_email('alice@example.com')
        r = self.alice.verify_email(email_row.id, nonce, self.alice)
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
        r = bob.verify_email(email_row.id, email_row.nonce, self.alice)
        assert r == EmailVerificationResult.FAILED

    def test_verify_email_a_second_time_returns_redundant(self):
        address = 'alice@example.com'
        self.hit_email_spt('add-email', address)
        email_row = self.alice.get_email(address)
        r = self.alice.verify_email(email_row.id, email_row.nonce, ANON)
        r = self.alice.verify_email(email_row.id, email_row.nonce, ANON)
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
        r = self.alice.verify_email(email_row.id, email_row.nonce, self.alice)
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
        r = self.alice.verify_email(email_row.id, email_row.nonce, ANON)
        assert r == EmailVerificationResult.LOGIN_REQUIRED
        actual = self.alice.refetch().email
        assert actual == None
        r = self.alice.verify_email(email_row.id, email_row.nonce, self.alice)
        assert r == EmailVerificationResult.SUCCEEDED

    def test_verify_email_doesnt_leak_whether_an_email_is_linked_to_an_account_or_not(self):
        self.alice.add_email('alice@example.com')
        email_row_alice = self.alice.get_email('alice@example.com')
        bob = self.make_participant('bob', email='bob@example.com')
        email_row_bob = bob.get_email(bob.email)
        r1 = self.alice.verify_email(email_row_alice.id, 'bad nonce', ANON)
        assert r1 == EmailVerificationResult.FAILED
        self.db.run("""
            UPDATE emails
               SET added_time = (now() - INTERVAL '2 years')
             WHERE participant = %s
        """, (self.alice.id,))
        r2 = self.alice.verify_email(email_row_alice.id, 'bad nonce', ANON)
        assert r2 == EmailVerificationResult.FAILED
        r3 = bob.verify_email(email_row_bob.id, 'bad nonce', ANON)
        assert r3 == EmailVerificationResult.FAILED

    def test_verify_email(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        nonce = self.alice.get_email('alice@example.com').nonce
        self.hit_verify('alice@example.com', nonce)
        expected = 'alice@example.com'
        actual = Participant.from_username('alice').email
        assert expected == actual

    def test_verify_email_with_unicode_domain(self):
        punycode_email = 'alice@' + 'accentué.fr'.encode('idna').decode()
        self.alice.add_email(punycode_email)
        nonce = self.alice.get_email(punycode_email).nonce
        self.hit_verify(punycode_email, nonce)
        actual = Participant.from_username('alice').email
        assert punycode_email == actual

    def test_verified_email_is_not_changed_after_update(self):
        self.add_and_verify_email('alice@example.com')
        self.alice.add_email('alice@example.net')
        expected = 'alice@example.com'
        actual = Participant.from_username('alice').email
        assert expected == actual

    def test_disavow_email(self):
        self.alice.add_email('alice@liberapay.com')
        email = self.alice.get_email('alice@liberapay.com')
        url = '/alice/emails/disavow?email.id=%s&email.nonce=%s' % (email.id, email.nonce)
        verification_email = self.get_last_email()
        assert url in verification_email['text']
        r = self.client.GET(url)
        assert r.code == 200
        email = self.alice.get_email(email.address)
        assert email.disavowed is True
        assert email.disavowed_time is not None
        assert email.verified is None
        assert email.verified_time is None
        assert email.nonce

        # Check idempotency
        r = self.client.GET(url)
        assert r.code == 200

        # Check that resending the verification email isn't allowed
        r = self.hit_email_spt('resend', email.address)
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
        r = self.alice.verify_email(email_row.id, email_row.nonce, ANON)
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
        assert self.mailer.call_count == 1
        last_email = self.get_last_email()
        assert last_email['to'][0] == 'larry <larry@example.com>'
        assert self.db.one("SELECT email_sent FROM notifications") is True

    def test_dequeueing_an_email_without_address_just_skips_it(self):
        larry = self.make_participant('larry')
        self.queue_email(larry, 'team_invite', team='team', team_url='fake_url', inviter='bob')

        Participant.dequeue_emails()
        assert self.mailer.call_count == 0
        assert self.db.one("SELECT email_sent FROM notifications") is False
