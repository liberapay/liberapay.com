from email.utils import parsedate
from http.cookies import SimpleCookie
from time import gmtime

from babel.messages.catalog import Message

from liberapay.constants import SESSION
from liberapay.i18n.base import LOCALES
from liberapay.models.participant import Participant
from liberapay.security.csrf import CSRF_TOKEN
from liberapay.testing import postgres_readonly
from liberapay.testing.emails import EmailHarness


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

    def test_email_login(self):
        email = 'alice@example.net'
        alice = self.make_participant('alice', email=None)
        alice.add_email(email)
        alice.close(None)

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
        r = self.client.GxT('/alice/' + refresh_qs)
        assert r.code == 302
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
        alice2 = Participant.authenticate(alice.id, 0, password)
        assert alice2 and alice2 == alice

    def test_email_login_with_old_unverified_address(self):
        email = 'alice@example.net'
        alice = self.make_participant('alice', email=None)
        alice.add_email(email)
        Participant.dequeue_emails()
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

        # Log in
        r = self.client.GxT('/alice/?' + qs)
        assert r.code == 302
        assert r.headers[b'Location'].startswith(b'http://localhost/alice/')

        # Check that the email address is now verified
        email_row = alice.get_email(email)
        assert email_row.verified
        alice = alice.refetch()
        assert alice.email == email

    def test_email_login_bad_email(self):
        data = {'log-in.id': 'unknown@example.org'}
        r = self.client.POST('/sign-in', data, raise_immediately=False)
        assert r.code != 302
        assert SESSION not in r.headers.cookie
        Participant.dequeue_emails()
        assert not self.get_emails()

    def test_email_login_bad_id(self):
        r = self.client.GxT('/?log-in.id=1&log-in.token=x')
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

    def test_email_login_bad_token(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        url = '/?log-in.id=%s&log-in.token=x' % alice.id
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
        alice.session = alice.start_session()
        assert alice.session.id == 1

        # Initiate a normal session, to be invalidated
        session2 = alice.start_session()
        assert session2.id == 2

        # Change the password
        alice.update_password('correct horse battery staple')

        # The second session should no longer be valid, but the initial session
        # should still be valid, and the account's password should not have
        # been deleted
        secret_ids = set(self.db.all(
            "SELECT id FROM user_secrets WHERE participant = %s", (alice.id,)
        ))
        assert secret_ids == {0, 1}


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
