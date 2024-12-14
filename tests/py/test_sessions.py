from email.utils import parsedate
from hashlib import blake2b
from http.cookies import SimpleCookie
from time import gmtime

from babel.messages.catalog import Message

from liberapay.constants import SESSION
from liberapay.i18n.base import LOCALES
from liberapay.i18n.currencies import Money
from liberapay.models.participant import Participant
from liberapay.security.csrf import CSRF_TOKEN
from liberapay.testing import Harness, postgres_readonly
from liberapay.testing.emails import EmailHarness
from liberapay.utils import b64encode_s, find_files


password = 'password'

good_data = {
    'sign-in.username': 'bob',
    'sign-in.password': password,
    'sign-in.email': 'bob@example.com',
    'sign-in.token': 'ThisIsATokenThatIsThirtyTwoBytes',
}


class TestLogIn(EmailHarness):

    def log_in(self, username, password, url='/sign-in', extra={}, **kw):
        data = {'log-in.id': username, 'log-in.password': password}
        data.update(extra)
        return self.client.POST(url, data, raise_immediately=False, **kw)

    def log_in_and_check(self, p, password, **kw):
        r = self.log_in(p.username, password, **kw)
        self.check_login(r, p)

    def check_login(self, r, p):
        # Basic checks
        assert r.code == 302
        session = self.db.one("""
            SELECT id, secret, mtime
              FROM user_secrets
             WHERE participant = %s
               AND id = 1
        """, (p.id,))
        expected = '%i:%i:%s' % (p.id, session.id, session.secret)
        sess_cookie = r.headers.cookie[SESSION]
        assert sess_cookie.value == expected
        expires = sess_cookie['expires']
        assert expires.endswith(' GMT')
        assert parsedate(expires) > gmtime()
        # More thorough check
        self.check_with_about_me(p.username, r.headers.cookie)

    def check_with_about_me(self, username, cookies):
        r = self.client.GET('/about/me/', cookies=cookies, raise_immediately=False)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/' + username.encode() + b'/'

    def test_log_in(self):
        alice = self.make_participant('alice')
        alice.update_password(password)
        self.log_in_and_check(alice, password)

    def test_log_in_form_repost(self):
        alice = self.make_participant('alice')
        alice.update_password(password)
        extra = {'name': 'python', 'lang': 'mul', 'form.repost': 'true'}
        r = self.log_in('alice', password, url='/for/new', extra=extra)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/for/python/edit'

    def test_log_in_with_email_as_id(self):
        email = 'alice@example.net'
        alice = self.make_participant('alice')
        alice.add_email(email)
        bob = self.make_participant('bob', email=email)
        bob.update_password(password)
        r = self.log_in(email, password)
        self.check_login(r, bob)

    def test_log_in_with_old_session(self):
        alice = self.make_participant('alice')
        self.db.run("UPDATE user_secrets SET mtime = mtime - interval '1 day'")
        alice.authenticated = True
        cookies = SimpleCookie()
        alice.sign_in(cookies)
        self.check_with_about_me('alice', cookies)

    def test_log_in_switch_user(self):
        alice = self.make_participant('alice')
        alice.update_password(password)
        bob = self.make_participant('bob')
        bob.authenticated = True
        cookies = SimpleCookie()
        bob.sign_in(cookies)
        self.log_in_and_check(alice, password, cookies=cookies)

    def test_log_in_closed_account(self):
        alice = self.make_participant('alice')
        alice.update_password(password)
        alice.update_status('closed')
        self.log_in_and_check(alice, password)
        alice2 = alice.refetch()
        assert alice2.status == 'active'
        assert alice2.join_time == alice.join_time

    def test_log_in_bad_username(self):
        r = self.log_in('alice', 'password')
        assert SESSION not in r.headers.cookie

    def test_log_in_no_password(self):
        stub = self.make_stub()
        r = self.log_in(stub.username, '')
        assert SESSION not in r.headers.cookie

    def test_log_in_bad_password(self):
        alice = self.make_participant('alice')
        alice.update_password('password')
        r = self.log_in('alice', 'deadbeef')
        assert SESSION not in r.headers.cookie

    def test_log_in_non_ascii_password(self):
        password = 'le blé pousse dans le champ'
        alice = self.make_participant('alice')
        alice.update_password(password)
        self.log_in_and_check(alice, password.encode('utf8'))

    def test_password_is_checked_during_log_in(self):
        password = 'password'
        alice = self.make_participant('alice')
        alice.update_password(password, checked=False)
        # Log in twice, the password should only be checked once
        self.log_in('alice', password)
        self.log_in('alice', password)
        notifs = alice.render_notifications(dict(_=str.format))
        assert len(notifs) == 1
        notif = notifs[0]
        assert notif['subject'] == "The password of your Liberapay account is weak"
        assert notif['type'] == "warning"

    def test_trying_to_log_in_to_passwordless_account_with_a_password(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        r = self.log_in(alice.email, 'password', url='/alice/edit')
        assert "Your account doesn&#39;t have a password" in r.text, r.text
        r = self.log_in(alice.email, 'password', url='/log-in')
        assert "Your account doesn&#39;t have a password" in r.text, r.text
        r = self.log_in(alice.email, 'password', url='/sign-in')
        assert "Your account doesn&#39;t have a password" in r.text, r.text

    def test_email_login(self):
        email = 'alice@example.net'
        alice = self.make_participant('alice', email=None)
        alice.add_email(email)
        alice.close()
        self.db.run("DELETE FROM user_secrets")

        # Sanity checks
        email_row = alice.get_email(email)
        assert email_row.verified is None
        assert alice.email is None

        # Initiate email log-in
        data = {'log-in.id': email.upper()}
        r = self.client.POST('/', data, raise_immediately=False)
        session = self.db.one("SELECT * FROM user_secrets WHERE participant = %s", (alice.id,))
        assert session.secret not in r.headers.raw.decode('ascii')
        assert session.secret not in r.body.decode('utf8')

        # Check the email message
        Participant.dequeue_emails()
        last_email = self.get_last_email()
        assert last_email and last_email['subject'] == 'Log in to Liberapay'
        qs = 'log-in.id=%i&log-in.key=%i&log-in.token=%s&email.id=%s&email.nonce=%s' % (
            alice.id, session.id, session.secret, email_row.id, email_row.nonce
        )
        assert qs in last_email['text']

        # Attempt to use the URL in a new browser session (no anti-CSRF cookie yet)
        r = self.client.GxT('/alice/?foo=bar&' + qs, csrf_token=None)
        assert r.code == 200
        refresh_qs = '?foo=bar&' + qs + '&cookie_sent=true'
        assert r.headers[b'Refresh'] == b"0;url=" + refresh_qs.encode()
        assert CSRF_TOKEN in r.headers.cookie

        # Follow the redirect, still without cookies
        r = self.client.GxT('/alice/' + refresh_qs, csrf_token=None)
        assert r.code == 403, r.text
        assert "Please make sure your browser is configured to allow cookies" in r.text

        # Log in
        csrf_token = '_ThisIsAThirtyTwoBytesLongToken_'
        confirmation_token = b64encode_s(blake2b(
            session.secret.encode(), key=csrf_token.encode(), digest_size=48,
        ).digest())
        r = self.client.GxT('/alice/' + refresh_qs, csrf_token=csrf_token)
        assert r.code == 200
        assert SESSION not in r.headers.cookie
        assert confirmation_token in r.text
        r = self.client.GxT(
            '/alice/' + refresh_qs + '&log-in.confirmation=' + confirmation_token,
            csrf_token=csrf_token,
        )
        assert r.code == 302
        assert SESSION in r.headers.cookie
        assert r.headers[b'Location'].startswith(
            b'http://localhost/alice/?foo=bar&success='
        )
        # ↑ checks that original path and query are preserved

        old_secret = self.db.one("""
            SELECT secret
              FROM user_secrets
             WHERE participant = %s
               AND id = %s
               AND secret = %s
        """, (alice.id, session.id, session.secret))
        assert old_secret is None
        # ↑ this means that the link is only valid once

        # Check that the email address is now verified
        email_row = alice.get_email(email)
        assert email_row.verified
        alice = alice.refetch()
        assert alice.email == email

        # Check what happens if the user clicks the login link a second time
        cookies = r.headers.cookie
        r = self.client.GxT('/alice/?foo=bar&' + qs, cookies=cookies)
        assert r.code == 400
        assert " already logged in," in r.text, r.text

        # Check that we can change our password
        password = 'correct-horse-battery-staple'
        r = self.client.POST(
            '/alice/settings/edit',
            {'new-password': password},
            cookies=cookies,
            raise_immediately=False,
        )
        assert r.code == 302
        alice2 = Participant.authenticate_with_password(alice.id, password)
        assert alice2 and alice2 == alice

    def test_email_login_with_old_unverified_address(self):
        email = 'alice@example.net'
        alice = self.make_participant('alice', email=None)
        alice.add_email(email)
        Participant.dequeue_emails()
        self.db.run("DELETE FROM user_secrets")
        self.db.run("UPDATE emails SET nonce = null")

        # Initiate email log-in
        data = {'log-in.id': email.upper()}
        r = self.client.POST('/', data, raise_immediately=False)
        session = self.db.one("SELECT * FROM user_secrets WHERE participant = %s", (alice.id,))
        assert session.secret not in r.headers.raw.decode('ascii')
        assert session.secret not in r.body.decode('utf8')

        # Check the email message
        Participant.dequeue_emails()
        last_email = self.get_last_email()
        assert last_email and last_email['subject'] == 'Log in to Liberapay'
        email_row = alice.get_email(email)
        assert email_row.verified is None
        assert email_row.nonce
        qs = 'log-in.id=%i&log-in.key=%i&log-in.token=%s&email.id=%s&email.nonce=%s' % (
            alice.id, session.id, session.secret, email_row.id, email_row.nonce
        )
        assert qs in last_email['text']

        # Try to log in without a confirmation code
        csrf_token = '_ThisIsAThirtyTwoBytesLongToken_'
        confirmation_token = b64encode_s(blake2b(
            session.secret.encode(), key=csrf_token.encode(), digest_size=48,
        ).digest())
        r = self.client.GxT('/alice/?' + qs, csrf_token=csrf_token)
        assert r.code == 200
        assert SESSION not in r.headers.cookie
        assert confirmation_token in r.text

        # Try to log in with an incorrect confirmation code
        r = self.client.GxT(
            '/alice/?' + qs + '&log-in.confirmation=' + ('~' * 64),
            csrf_token=csrf_token,
        )
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        assert confirmation_token not in r.text

        # Log in with the correct confirmation code
        r = self.client.GxT(
            '/alice/?' + qs + '&log-in.confirmation=' + confirmation_token,
            csrf_token=csrf_token,
        )
        assert r.code == 302
        assert SESSION in r.headers.cookie
        assert r.headers[b'Location'].startswith(b'http://localhost/alice/')

        # Check that the email address is now verified
        email_row = alice.get_email(email)
        assert email_row.verified
        alice = alice.refetch()
        assert alice.email == email

    def test_email_login_cancellation(self):
        email = 'alice@example.net'
        alice = self.make_participant('alice', email=email)

        # Initiate the log-in
        data = {'log-in.id': email.title()}
        r = self.client.POST('/', data, raise_immediately=False)
        session = self.db.one("SELECT * FROM user_secrets WHERE participant = %s", (alice.id,))
        assert session.secret not in r.headers.raw.decode('ascii')
        assert session.secret not in r.body.decode('utf8')

        # Open the log-in URL
        qs = '?log-in.id=%i&log-in.key=%i&log-in.token=%s' % (
            alice.id, session.id, session.secret
        )
        r = self.client.GxT('/alice/' + qs)
        assert r.code == 200
        assert SESSION not in r.headers.cookie
        assert 'log-in.cancel=yes' in r.text

        # Cancel the log-in
        r = self.client.GxT('/alice/' + qs + '&log-in.cancel=yes')
        assert r.code == 200
        assert SESSION not in r.headers.cookie
        old_secret = self.db.one("""
            SELECT secret
              FROM user_secrets
             WHERE participant = %s
               AND id = %s
               AND secret = %s
        """, (alice.id, session.id, session.secret))
        assert old_secret is None

    def test_email_login_bad_email(self):
        data = {'log-in.id': 'unknown@example.org'}
        r = self.client.POST('/sign-in', data, raise_immediately=False)
        assert r.code != 302
        assert SESSION not in r.headers.cookie
        Participant.dequeue_emails()
        assert not self.get_emails()

    def test_email_login_bad_id(self):
        r = self.client.GxT('/?log-in.id=x&log-in.key=1001&log-in.token=x')
        assert r.code == 400

    def test_email_login_bad_key(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        email_session = alice.start_session('.em')
        url = '/about/me/?log-in.id=%s&log-in.key=%i&log-in.token=%s' % (
            alice.id, email_session.id + 1, email_session.secret
        )
        r = self.client.GxT(url)
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        r = self.client.GxT(url, auth_as=alice)
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        r = self.client.GxT(url, auth_as=bob)
        assert r.code == 400
        assert SESSION not in r.headers.cookie

    def test_email_login_missing_key(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        email_session = alice.start_session('.em')
        url = f'/about/me/?log-in.id={alice.id}&log-in.token={email_session.secret}'
        r = self.client.GxT(url)
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        r = self.client.GxT(url, auth_as=alice)
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        r = self.client.GxT(url, auth_as=bob)
        assert r.code == 400
        assert SESSION not in r.headers.cookie

    def test_email_login_bad_token(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        email_session = alice.start_session('.em')
        url = '/about/me/?log-in.id=%s&log-in.key=%i&log-in.token=%s' % (
            alice.id, email_session.id, email_session.secret + '!'
        )
        r = self.client.GxT(url)
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        r = self.client.GxT(url, auth_as=alice)
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        r = self.client.GxT(url, auth_as=bob)
        assert r.code == 400
        assert SESSION not in r.headers.cookie

    def test_email_login_missing_token(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        email_session = alice.start_session('.em')
        url = f'/about/me/?log-in.id={alice.id}&log-in.key={email_session.id}'
        r = self.client.GxT(url)
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        r = self.client.GxT(url, auth_as=alice)
        assert r.code == 400
        assert SESSION not in r.headers.cookie
        r = self.client.GxT(url, auth_as=bob)
        assert r.code == 400
        assert SESSION not in r.headers.cookie

    def test_email_login_team_account(self):
        email = 'team@example.net'
        self.make_participant('team', email=email, kind='group')
        data = {'log-in.id': email}
        r = self.client.POST('/log-in', data, raise_immediately=False)
        assert SESSION not in r.headers.cookie
        Participant.dequeue_emails()
        assert not self.get_emails()

    def test_carrying_on_after_email_login(self):
        email = 'alice@example.net'
        alice = self.make_participant('alice', email=email)

        # Initiate the log-in
        data = {'log-in.id': email.upper()}
        r = self.client.POST('/?foo=bar', data, raise_immediately=False, HTTP_ACCEPT=b'text/html')
        session = self.db.one("SELECT * FROM user_secrets WHERE participant = %s", (alice.id,))
        assert session.secret not in r.headers.raw.decode('ascii')
        assert session.secret not in r.body.decode('utf8')
        assert r.headers[b'Content-Type'] == b'text/html; charset=UTF-8'
        assert "Carry on" in r.text

        # Log in, in another tab
        qs = '?log-in.id=%i&log-in.key=%i&log-in.token=%s' % (
            alice.id, session.id, session.secret
        )
        csrf_token = '_ThisIsAThirtyTwoBytesLongToken_'
        confirmation_token = b64encode_s(blake2b(
            session.secret.encode(), key=csrf_token.encode(), digest_size=48,
        ).digest())
        r = self.client.GxT(
            '/alice/' + qs + '&log-in.confirmation=' + confirmation_token,
            csrf_token=csrf_token,
        )
        assert r.code == 302
        assert SESSION in r.headers.cookie

        # Carry on in the first tab
        data['log-in.carry-on'] = email
        r = self.client.POST(
            '/?foo=bar',
            data,
            auth_as=alice,
            raise_immediately=False,
            HTTP_ACCEPT=b'text/html',
        )
        assert r.code == 302
        assert r.headers[b'Location'] == b'http://localhost/?foo=bar'

    def test_carrying_on_with_form_submission_after_email_login(self):
        email = 'alice@example.net'
        alice = self.make_participant('alice', email=email)

        # Initiate the log-in
        data = {'log-in.id': email.upper()}
        r = self.client.POST('/?foo=bar', data, raise_immediately=False, HTTP_ACCEPT=b'text/html')
        session = self.db.one("SELECT * FROM user_secrets WHERE participant = %s", (alice.id,))
        assert session.secret not in r.headers.raw.decode('ascii')
        assert session.secret not in r.body.decode('utf8')
        assert r.headers[b'Content-Type'] == b'text/html; charset=UTF-8'
        assert "Carry on" in r.text
        assert 'name="form.repost" value="true"' in r.text

        # Log in, in another tab
        qs = '?log-in.id=%i&log-in.key=%i&log-in.token=%s' % (
            alice.id, session.id, session.secret
        )
        csrf_token = '_ThisIsAThirtyTwoBytesLongToken_'
        confirmation_token = b64encode_s(blake2b(
            session.secret.encode(), key=csrf_token.encode(), digest_size=48,
        ).digest())
        r = self.client.GxT(
            '/alice/' + qs + '&log-in.confirmation=' + confirmation_token,
            csrf_token=csrf_token,
        )
        assert r.code == 302
        assert SESSION in r.headers.cookie

        # Carry on in the first tab
        data['form.repost'] = 'true'
        data['log-in.carry-on'] = email
        r = self.client.POST(
            '/?foo=bar',
            data,
            auth_as=alice,
            raise_immediately=False,
            HTTP_ACCEPT=b'text/html',
        )
        assert r.code == 200

    def test_normal_session_cannot_be_escalated_to_email_session(self):
        alice = self.make_participant('alice')
        session = alice.start_session()
        r = self.client.GxT(
            '/about/me/?log-in.id=%s&log-in.key=%i&log-in.token=%s' % (
                alice.id, session.id, session.secret
            )
        )
        assert r.code == 400
        assert SESSION not in r.headers.cookie

    def test_email_sessions_are_invalidated_when_primary_email_is_changed(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        email2 = self.insert_email('alice@example.com', alice.id, verified=True)
        password = self.db.one("""
            INSERT INTO user_secrets
                        (participant, id, secret)
                 VALUES (%s, %s, %s)
              RETURNING *
        """, (alice.id, 0, 'irrelevant'))

        # Get a first active email session
        alice.session = alice.start_session(suffix='.em', id_min=1001, id_max=1010)
        assert alice.session.id == 1001

        # Initiate a second email session, to be invalidated
        session2 = alice.start_session(suffix='.em', id_min=1001, id_max=1010)
        assert session2.id == 1002

        # Change the primary email address
        alice.update_email(email2.address)

        # The second email session should no longer be valid, but the first
        # session should still be valid, and the account's password should not
        # have been deleted
        secrets = dict(self.db.all(
            "SELECT id, secret FROM user_secrets WHERE participant = %s", (alice.id,)
        ))
        assert secrets == {
            0: password.secret,
            1001: alice.session.secret,
        }

    def test_normal_sessions_are_invalidated_when_password_is_changed(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        alice.update_password('password')

        # Get an initial session
        alice.session = alice.start_session(suffix='.in')
        assert alice.session.id == 1

        # Get a password session, to be invalidated
        session2 = alice.start_session(suffix='.pw')
        assert session2.id == 2

        # Get a read-only session, to be invalidated
        session3 = alice.start_session(suffix='.ro')
        assert session3.id == 3

        # Get an email session
        session3 = alice.start_session(suffix='.em', id_min=1001, id_max=1010)
        assert session3.id == 1001

        # Change the password
        form_data = {
            'cur-password': 'password',
            'new-password': 'correct horse battery staple',
            'ignore_warning': 'true',
        }
        r = self.client.PxST('/alice/settings/edit', form_data, auth_as=alice)
        assert r.code == 302, r.text

        # Only the initial and email sessions should still be valid, and of
        # course the account's password should not have been deleted
        secret_ids = set(self.db.all(
            "SELECT id FROM user_secrets WHERE participant = %s", (alice.id,)
        ))
        assert secret_ids == {0, 1, 1001}


class TestSignIn(EmailHarness):

    def sign_in(self, custom={}, extra={}, url='/sign-in', **kw):
        data = dict(good_data, **extra)
        for k, v in custom.items():
            if v is None:
                del data['sign-in.'+k]
                continue
            data['sign-in.'+k] = v
        kw.setdefault('raise_immediately', False)
        return self.client.POST(url, data, **kw)

    def test_sign_in(self):
        fake_msg = Message('Email address verification - Liberapay', 'Vous avez du pain ?')
        LOCALES['fr'].catalog[fake_msg.id].string = fake_msg.string
        r = self.sign_in(HTTP_ACCEPT_LANGUAGE='fr')
        assert r.code == 302, r.text
        assert SESSION in r.headers.cookie
        # Check that an email was sent, in the user's preferred language
        Participant.dequeue_emails()
        last_email = self.get_last_email()
        username = good_data['sign-in.username']
        assert last_email['subject'] == fake_msg.string
        # Check that the new user has an avatar
        p = Participant.from_username(username)
        assert p.avatar_url
        # Simulate a double submit
        r2 = self.sign_in(HTTP_ACCEPT_LANGUAGE='fr')
        assert r2.code == 302, r2.text
        assert r2.headers.cookie[SESSION].value == r.headers.cookie[SESSION].value

    def test_sign_in_form_repost(self):
        extra = {'name': 'python', 'lang': 'mul', 'form.repost': 'true'}
        r = self.sign_in(url='/for/new', extra=extra)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/for/python/edit'

    def test_sign_in_through_donation_form(self):
        alice = self.make_participant('alice', accepted_currencies=None)
        extra = {'amount': '10000', 'currency': 'KRW', 'period': 'weekly', 'form.repost': 'true'}
        r = self.sign_in(url='/~1/tip', extra=extra)
        assert r.code == 302, r.text
        assert r.headers[b'Location'].startswith(b'http://localhost/bob/giving/')
        bob = Participant.from_username('bob')
        tip = bob.get_tip_to(alice)
        assert tip.amount == Money('10000', 'KRW')
        assert bob.main_currency == 'KRW'

    def test_sign_in_without_username(self):
        r = self.sign_in(dict(username=''))
        assert r.code == 302
        assert SESSION in r.headers.cookie
        # Simulate a double submit
        r2 = self.sign_in(dict(username=''))
        assert r2.code == 302, r2.text
        assert r2.headers.cookie[SESSION].value == r.headers.cookie[SESSION].value

    def test_sign_in_non_ascii_username(self):
        r = self.sign_in(dict(username='mélodie'.encode('utf8')))
        assert r.code == 400

    def test_sign_in_non_ascii_password(self):
        r = self.sign_in(dict(password='super clé'.encode('utf8')))
        assert r.code == 302

    def test_sign_in_long_username(self):
        r = self.sign_in(dict(username='a'*200))
        assert r.code == 400

    def test_sign_in_restricted_username(self):
        r = self.sign_in(dict(username='about'))
        assert r.code == 400

    def test_sign_in_without_password(self):
        r = self.sign_in(dict(password=''))
        assert r.code == 302

    def test_sign_in_short_password(self):
        r = self.sign_in(dict(password='a'))
        assert r.code == 400

    def test_sign_in_long_password(self):
        r = self.sign_in(dict(password='a'*200))
        assert r.code == 400

    def test_sign_in_bad_kind(self):
        r = self.sign_in(dict(kind='group'))
        assert r.code == 400

    def test_sign_in_bad_email(self):
        r = self.sign_in(dict(email='foo@bar'))
        assert r.code == 400

    def test_sign_in_email_already_taken_just_now(self):
        r = self.sign_in()
        assert r.code == 302
        r = self.sign_in(dict(username=None, token='0'*32))
        assert r.code == 409
        assert SESSION not in r.headers.cookie
        r = self.sign_in(dict(username=None, token=''))
        assert r.code == 409
        assert SESSION not in r.headers.cookie
        r = self.sign_in(dict(username=None, token=None))
        assert r.code == 409
        assert SESSION not in r.headers.cookie

    def test_sign_in_email_already_taken_a_while_ago(self):
        r = self.sign_in()
        assert r.code == 302
        self.db.run("UPDATE participants SET join_time = join_time - interval '1 week'")
        self.db.run("UPDATE user_secrets SET mtime = mtime - interval '1 week'")
        r = self.sign_in(dict(username=None, token='0'*32))
        assert r.code == 409
        assert SESSION not in r.headers.cookie
        r = self.sign_in(dict(username=None, token=''))
        assert r.code == 409
        assert SESSION not in r.headers.cookie
        r = self.sign_in(dict(username=None, token=None))
        assert r.code == 409
        assert SESSION not in r.headers.cookie

    def test_sign_in_without_csrf_cookie(self):
        r = self.sign_in(csrf_token=None)
        assert r.code == 403
        assert "cookie" in r.text
        assert SESSION not in r.headers.cookie

    def test_sign_in_when_db_is_read_only(self):
        with postgres_readonly(self.db):
            r = self.sign_in(HTTP_ACCEPT=b'text/html')
            assert r.code == 503, r.text
            assert 'read-only' in r.text


class TestSessions(Harness):

    def test_session_cookie_is_secure_if_it_should_be(self):
        canonical_scheme = self.client.website.canonical_scheme
        self.client.website.canonical_scheme = 'https'
        try:
            cookies = SimpleCookie()
            alice = self.make_participant('alice')
            alice.authenticated = True
            alice.sign_in(cookies)
            assert '; secure' in cookies[SESSION].output().lower()
        finally:
            self.client.website.canonical_scheme = canonical_scheme

    def test_session_is_downgraded_to_read_only_after_a_little_while(self):
        alice = self.make_participant('alice')
        initial_session = alice.session = alice.start_session(suffix='.em')
        self.db.run("UPDATE user_secrets SET mtime = mtime - interval '7 hours'")
        r = self.client.GET('/alice/edit/username', auth_as=alice)
        assert r.code == 200, r.text
        new_session_id, new_session_secret = r.headers.cookie[SESSION].value.split(':')[1:]
        assert int(new_session_id) == initial_session.id
        assert new_session_secret != initial_session.secret
        assert new_session_secret.endswith('.ro')

    def test_read_only_session_eventually_expires(self):
        alice = self.make_participant('alice')
        alice.session = alice.start_session(suffix='.ro')
        self.db.run("UPDATE user_secrets SET mtime = mtime - interval '40 days'")
        r = self.client.GET('/alice/edit/username', auth_as=alice, raise_immediately=False)
        assert r.code == 403, r.text
        assert r.headers.cookie[SESSION].value == f'{alice.id}:!:'
        r = self.client.GET(
            '/alice/edit/username',
            HTTP_COOKIE=f"session={alice.id}:!:",
            raise_immediately=False,
        )
        assert r.code == 403, r.text

    def test_long_lived_session_tokens_are_regularly_regenerated(self):
        alice = self.make_participant('alice')
        alice.authenticated = True
        initial_session = alice.session = alice.start_session(suffix='.ro')
        r = self.client.GET('/', auth_as=alice)
        assert r.code == 200, r.text
        assert SESSION not in r.headers.cookie
        alice.session = self.db.one("""
            UPDATE user_secrets
               SET mtime = mtime - interval '12 hours'
             WHERE participant = %s
         RETURNING id, secret, mtime
        """, (alice.id,))
        r = self.client.GET('/', auth_as=alice)
        assert r.code == 200, r.text
        new_session_id, new_session_secret = r.headers.cookie[SESSION].value.split(':')[1:]
        assert int(new_session_id) == initial_session.id
        assert new_session_secret != initial_session.secret
        assert new_session_secret.endswith('.ro')

    def test_read_only_sessions_are_not_admin_sessions(self):
        alice = self.make_participant('alice', privileges=1)
        alice.session = alice.start_session(suffix='.ro')
        i = len(self.client.www_root)
        def f(spt):
            if spt[spt.rfind('/')+1:].startswith('index.'):
                return spt[i:spt.rfind('/')+1]
            return spt[i:-4]
        for url in sorted(map(f, find_files(self.client.www_root+'/admin', '*.spt'))):
            r = self.client.GxT(url, auth_as=alice)
            assert r.code == 403, r.text
        self.make_participant('bob')
        r = self.client.GxT('/bob/admin', auth_as=alice)
        assert r.code == 403, r.text
        r = self.client.GxT('/bob/giving/', auth_as=alice)
        assert r.code == 403, r.text

    def test_a_read_only_session_can_be_used_to_view_an_account_but_not_modify_it(self):
        alice = self.make_participant('alice')
        alice.session = alice.start_session(suffix='.ro')
        r = self.client.GET('/alice/edit/username', auth_as=alice)
        assert r.code == 200, r.text
        r = self.client.PxST('/alice/edit/username', {}, auth_as=alice)
        assert r.code == 403, r.text

    def test_constant_sessions(self):
        alice = self.make_participant('alice')
        r = self.client.GET('/alice/access/constant-session', auth_as=alice)
        assert r.code == 200, r.text
        constant_sessions = self.db.all("""
            SELECT *
              FROM user_secrets
             WHERE participant = %s
               AND id >= 800
        """, (alice.id,))
        assert not constant_sessions
        del constant_sessions
        # Test creating the constant session
        r = self.client.PxST(
            '/alice/access/constant-session',
            {'action': 'start'},
            auth_as=alice,
        )
        assert r.code == 302, r.text
        constant_session = self.db.one("""
            SELECT *
              FROM user_secrets
             WHERE participant = %s
               AND id >= 800
        """, (alice.id,))
        assert constant_session
        r = self.client.GET('/alice/access/constant-session', auth_as=alice)
        assert r.code == 200, r.text
        assert constant_session.secret in r.text
        # Test using the constant session
        r = self.client.GxT(
            '/about/me/',
            cookies={
                'session': f'{alice.id}:{constant_session.id}:{constant_session.secret}',
            },
        )
        assert r.code == 302, r.text
        # Test regenerating the constant session
        r = self.client.PxST(
            '/alice/access/constant-session',
            {'action': 'start'},
            auth_as=alice,
        )
        assert r.code == 302, r.text
        old_constant_session = constant_session
        constant_session = self.db.one("""
            SELECT *
              FROM user_secrets
             WHERE participant = %s
               AND id >= 800
        """, (alice.id,))
        assert constant_session
        assert constant_session.secret != old_constant_session.secret
        # Test expiration of the session
        self.db.run("""
            UPDATE user_secrets
               SET mtime = mtime - interval '300 days'
                 , latest_use = latest_use - interval '300 days'
             WHERE id = 800
        """)
        r = self.client.GxT(
            '/about/me/',
            cookies={
                'session': f'{alice.id}:{constant_session.id}:{constant_session.secret}',
            },
        )
        assert r.code == 302, r.text
        self.db.run("""
            UPDATE user_secrets
               SET mtime = mtime - interval '500 days'
                 , latest_use = latest_use - interval '500 days'
             WHERE id = 800
        """)
        r = self.client.GxT(
            '/about/me/',
            cookies={
                'session': f'{alice.id}:{constant_session.id}:{constant_session.secret}',
            },
        )
        assert r.code == 403, r.text
        # Test revoking the constant session
        r = self.client.PxST(
            '/alice/access/constant-session',
            {'action': 'end'},
            auth_as=alice,
        )
        assert r.code == 302, r.text
        constant_session = self.db.one("""
            SELECT *
              FROM user_secrets
             WHERE participant = %s
               AND id >= 800
        """, (alice.id,))
        assert not constant_session

    def test_invalid_session_cookies(self):
        r = self.client.GET('/about/me/', HTTP_COOKIE='session=::', raise_immediately=False)
        assert r.code == 403, r.text
        r = self.client.GET('/about/me/', HTTP_COOKIE='session=_:_:_', raise_immediately=False)
        assert r.code == 403, r.text
        r = self.client.GET('/about/me/', HTTP_COOKIE='session=0:0:0', raise_immediately=False)
        assert r.code == 403, r.text
        r = self.client.GET('/about/me/', HTTP_COOKIE='session=1:1:1', raise_immediately=False)
        assert r.code == 403, r.text
        alice = self.make_participant('alice')
        r = self.client.GET('/about/me/', HTTP_COOKIE=f'session={alice.id}::', raise_immediately=False)
        assert r.code == 403, r.text
        r = self.client.GET('/about/me/', HTTP_COOKIE=f'session={alice.id}:0:', raise_immediately=False)
        assert r.code == 403, r.text
        r = self.client.GET('/about/me/', HTTP_COOKIE=f'session={alice.id}:1:', raise_immediately=False)
        assert r.code == 403, r.text
        r = self.client.GET('/about/me/', HTTP_COOKIE=f'session={alice.id}:1:_', raise_immediately=False)
        assert r.code == 403, r.text
        session = alice.start_session(suffix='.pw')
        incorrect_secret = str(ord(session.secret[0]) ^ 1) + session.secret[1:]
        r = self.client.GET(
            '/about/me/',
            HTTP_COOKIE=f'session={alice.id}:{session.id}:{incorrect_secret}',
            raise_immediately=False,
        )
        assert r.code == 403, r.text
