from unittest.mock import patch

from liberapay.exceptions import (
    BadEmailAddress, BadEmailDomain, CannotRemovePrimaryEmail, EmailAlreadyTaken,
    EmailNotVerified, TooManyEmailAddresses, TooManyEmailVerifications,
)
from liberapay.models.participant import Participant
from liberapay.testing.emails import EmailHarness
from liberapay.utils import emails


class TestEmail(EmailHarness):

    def setUp(self):
        EmailHarness.setUp(self)
        self.alice = self.make_participant('alice')

    def hit_email_spt(self, action, address, auth_as='alice', should_fail=False):
        P = self.client.PxST if should_fail else self.client.POST
        if action == 'add-email':
            data = {'email': address}
        else:
            data = {action: address}
        headers = {'HTTP_ACCEPT_LANGUAGE': 'en', 'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        auth_as = self.alice if auth_as == 'alice' else auth_as
        return P('/alice/emails/modify.json', data, auth_as=auth_as, **headers)

    def get_address_id(self, addr):
        return self.db.one("SELECT id FROM emails WHERE address = %s", (addr,))

    def hit_verify(self, email, nonce, should_fail=False):
        addr_id = self.get_address_id(email) or ''
        url = '/alice/emails/verify.html?email=%s&nonce=%s' % (addr_id, nonce)
        G = self.client.GxT if should_fail else self.client.GET
        return G(url, auth_as=self.alice)

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
        assert self.alice.get_any_email() == punycode_email

    def test_participant_cannot_add_email_with_unicode_local_part(self):
        r = self.hit_email_spt('add-email', 'tête@exemple.fr', should_fail=True)
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
            response = self.hit_email_spt('add-email', blob, should_fail=True)
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
                response = self.hit_email_spt('add-email', email, should_fail=True)
                assert response.code == 400

    def test_verification_link_uses_address_id(self):
        address = 'alice@gratipay.com'
        self.hit_email_spt('add-email', address)
        addr_id = self.get_address_id(address)
        last_email = self.get_last_email()
        assert "/alice/emails/verify.html?email=%s&" % addr_id in last_email['text']

    def test_adding_email_sends_verification_email(self):
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
        response = self.hit_email_spt('add-email', 'anon@example.com', auth_as=None, should_fail=True)
        assert response.code == 403

    def test_post_with_no_at_symbol_is_400(self):
        response = self.hit_email_spt('add-email', 'example.com', should_fail=True)
        assert response.code == 400

    def test_post_with_no_period_symbol_is_400(self):
        response = self.hit_email_spt('add-email', 'test@example', should_fail=True)
        assert response.code == 400

    def test_verify_email_without_adding_email(self):
        response = self.hit_verify('', 'sample-nonce')
        assert 'Missing Info' in response.text

    def test_verify_email_wrong_nonce(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        nonce = 'fake-nonce'
        r = self.alice.verify_email('alice@example.com', nonce)
        assert r == emails.VERIFICATION_FAILED
        self.hit_verify('alice@example.com', nonce)
        expected = None
        actual = Participant.from_username('alice').email
        assert expected == actual

    def test_verify_email_a_second_time_returns_redundant(self):
        address = 'alice@example.com'
        self.hit_email_spt('add-email', address)
        nonce = self.alice.get_email(address).nonce
        r = self.alice.verify_email(address, nonce)
        r = self.alice.verify_email(address, nonce)
        assert r == emails.VERIFICATION_REDUNDANT

    def test_verify_email_expired_nonce(self):
        address = 'alice@example.com'
        self.hit_email_spt('add-email', address)
        self.db.run("""
            UPDATE emails
               SET added_time = (now() - INTERVAL '25 hours')
             WHERE participant = %s
        """, (self.alice.id,))
        nonce = self.alice.get_email(address).nonce
        r = self.alice.verify_email(address, nonce)
        assert r == emails.VERIFICATION_EXPIRED
        actual = Participant.from_username('alice').email
        assert actual == None

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
        nonce = self.alice.get_email('alice@example.com').nonce
        r = self.alice.verify_email('alice@example.com', nonce)
        assert r == emails.VERIFICATION_SUCCEEDED

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
        assert self.alice.get_any_email() == 'Alice&Bob@example.info'

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
            self.hit_email_spt('set-primary', 'alice@example.com')

    def test_remove_email(self):
        # Cannot remove unverified primary
        self.hit_email_spt('add-email', 'alice@example.com')
        with self.assertRaises(CannotRemovePrimaryEmail):
            self.hit_email_spt('remove', 'alice@example.com')

        # Can remove extra unverified
        self.hit_email_spt('add-email', 'alice@example.org')
        self.hit_email_spt('remove', 'alice@example.org')

        # Can remove extra verified
        self.verify_email('alice@example.com')
        self.add_and_verify_email('alice@example.net')
        self.hit_email_spt('remove', 'alice@example.net')

        # Cannot remove primary
        with self.assertRaises(CannotRemovePrimaryEmail):
            self.hit_email_spt('remove', 'alice@example.com')

    def test_html_escaping(self):
        self.alice.add_email("foo'bar@example.com")
        last_email = self.get_last_email()
        assert 'foo&#39;bar' in last_email['html']
        assert '&#39;' not in last_email['text']

    def queue_email(self, participant, event, **context):
        return participant.notify(event, force_email=True, web=False, **context)

    def test_can_dequeue_an_email(self):
        larry = self.make_participant('larry', email='larry@example.com')
        self.queue_email(larry, "verification", link='https://example.com/larry')

        assert self.db.one("SELECT event FROM notifications") == "verification"
        Participant.dequeue_emails()
        assert self.mailer.call_count == 1
        last_email = self.get_last_email()
        assert last_email['to'][0] == 'larry <larry@example.com>'
        assert last_email['subject'] == "Email address verification - Liberapay"
        assert self.db.one("SELECT email_sent FROM notifications") is True

    def test_dequeueing_an_email_without_address_just_skips_it(self):
        larry = self.make_participant('larry')
        self.queue_email(larry, "verification")

        assert self.db.one("SELECT event FROM notifications") == "verification"
        Participant.dequeue_emails()
        assert self.mailer.call_count == 0
        assert self.db.one("SELECT email_sent FROM notifications") is False
