from liberapay.exceptions import CannotRemovePrimaryEmail, EmailAlreadyTaken, EmailNotVerified
from liberapay.exceptions import TooManyEmailAddresses
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

    def verify_email(self, email, nonce, should_fail=False):
        url = '/alice/emails/verify.html?email=%s&nonce=%s' % (email, nonce)
        G = self.client.GxT if should_fail else self.client.GET
        return G(url, auth_as=self.alice)

    def verify_and_change_email(self, old_email, new_email):
        self.hit_email_spt('add-email', old_email)
        nonce = self.alice.get_email(old_email).nonce
        self.verify_email(old_email, nonce)
        self.hit_email_spt('add-email', new_email)

    def test_participant_can_add_email(self):
        response = self.hit_email_spt('add-email', 'alice@example.com')
        assert response.text == '{}'

    def test_adding_email_sends_verification_email(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        assert self.mailer.call_count == 1
        last_email = self.get_last_email()
        assert last_email['to'][0]['email'] == 'alice@example.com'
        expected = "We've received a request to connect alice@example.com to the alice account on Liberapay"
        assert expected in last_email['text']

    def test_adding_second_email_sends_verification_notice(self):
        self.verify_and_change_email('alice1@example.com', 'alice2@example.com')
        assert self.mailer.call_count == 3
        last_email = self.get_last_email()
        assert last_email['to'][0]['email'] == 'alice1@example.com'
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
        response = self.verify_email('', 'sample-nonce')
        assert 'Missing Info' in response.text

    def test_verify_email_wrong_nonce(self):
        self.hit_email_spt('add-email', 'alice@example.com')
        nonce = 'fake-nonce'
        r = self.alice.verify_email('alice@example.com', nonce)
        assert r == emails.VERIFICATION_FAILED
        self.verify_email('alice@example.com', nonce)
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
        self.verify_email('alice@example.com', nonce)
        expected = 'alice@example.com'
        actual = Participant.from_username('alice').email
        assert expected == actual

    def test_verified_email_is_not_changed_after_update(self):
        self.verify_and_change_email('alice@example.com', 'alice@example.net')
        expected = 'alice@example.com'
        actual = Participant.from_username('alice').email
        assert expected == actual

    def test_get_emails(self):
        self.verify_and_change_email('alice@example.com', 'alice@example.net')
        emails = self.alice.get_emails()
        assert len(emails) == 2

    def test_verify_email_after_update(self):
        self.verify_and_change_email('alice@example.com', 'alice@example.net')
        nonce = self.alice.get_email('alice@example.net').nonce
        self.verify_email('alice@example.net', nonce)
        expected = 'alice@example.com'
        actual = Participant.from_username('alice').email
        assert expected == actual

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
            bob.verify_email('alice@example.com', nonce)

        email_alice = Participant.from_username('alice').email
        assert email_alice == 'alice@example.com'

    def test_cannot_add_too_many_emails(self):
        self.alice.add_email('alice@example.com')
        self.alice.add_email('alice@example.net')
        self.alice.add_email('alice@example.org')
        self.alice.add_email('alice@example.co.uk')
        self.alice.add_email('alice@example.io')
        self.alice.add_email('alice@example.co')
        self.alice.add_email('alice@example.eu')
        self.alice.add_email('alice@example.asia')
        self.alice.add_email('alice@example.museum')
        self.alice.add_email('alice@example.py')
        with self.assertRaises(TooManyEmailAddresses):
            self.alice.add_email('alice@example.coop')

    def test_emails_page_shows_emails(self):
        self.verify_and_change_email('alice@example.com', 'alice@example.net')
        body = self.client.GET("/alice/emails/", auth_as=self.alice).text
        assert 'alice@example.com' in body
        assert 'alice@example.net' in body

    def test_set_primary(self):
        self.verify_and_change_email('alice@example.com', 'alice@example.net')
        self.verify_and_change_email('alice@example.net', 'alice@example.org')
        self.hit_email_spt('set-primary', 'alice@example.com')

    def test_cannot_set_primary_to_unverified(self):
        with self.assertRaises(EmailNotVerified):
            self.hit_email_spt('set-primary', 'alice@example.com')

    def test_remove_email(self):
        # Can remove unverified
        self.hit_email_spt('add-email', 'alice@example.com')
        self.hit_email_spt('remove', 'alice@example.com')

        # Can remove verified
        self.verify_and_change_email('alice@example.com', 'alice@example.net')
        self.verify_and_change_email('alice@example.net', 'alice@example.org')
        self.hit_email_spt('remove', 'alice@example.net')

        # Cannot remove primary
        with self.assertRaises(CannotRemovePrimaryEmail):
            self.hit_email_spt('remove', 'alice@example.com')

    def test_html_escaping(self):
        self.alice.add_email("foo'bar@example.com")
        last_email = self.get_last_email()
        assert 'foo&#39;bar' in last_email['html']
        assert '&#39;' not in last_email['text']

    def test_can_dequeue_an_email(self):
        larry = self.make_participant('larry', email='larry@example.com')
        larry.queue_email("verification")

        assert self.db.one("SELECT spt_name FROM email_queue") == "verification"
        Participant.dequeue_emails()
        assert self.mailer.call_count == 1
        last_email = self.get_last_email()
        assert last_email['to'][0]['email'] == 'larry@example.com'
        expected = "connect larry"
        assert expected in last_email['text']
        assert self.db.one("SELECT spt_name FROM email_queue") is None

    def test_dequeueing_an_email_without_address_just_skips_it(self):
        larry = self.make_participant('larry')
        larry.queue_email("verification")

        assert self.db.one("SELECT spt_name FROM email_queue") == "verification"
        Participant.dequeue_emails()
        assert self.mailer.call_count == 0
        assert self.db.one("SELECT spt_name FROM email_queue") is None
