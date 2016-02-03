# coding: utf8

from __future__ import division, print_function, unicode_literals

from liberapay.constants import SESSION
from liberapay.models.participant import Participant
from liberapay.testing.emails import EmailHarness


good_data = {
    'sign-in.username': 'bob',
    'sign-in.password': 'password',
    'sign-in.kind': 'individual',
    'sign-in.email': 'bob@example.com',
    'sign-in.terms': 'agree',
}


class TestSignIn(EmailHarness):

    def log_in(self, username, password):
        data = {'log-in.username': username, 'log-in.password': password}
        return self.client.POST('/sign-in', data, raise_immediately=False)

    def test_log_in(self):
        password = 'password'
        alice = self.make_participant('alice')
        alice.update_password(password)
        r = self.log_in('alice', password)
        assert r.code == 302
        assert SESSION in r.headers.cookie

    def test_log_in_closed_account(self):
        password = 'password'
        alice = self.make_participant('alice')
        alice.update_password(password)
        alice.update_status('closed')
        r = self.log_in('alice', password)
        assert r.code == 302
        assert SESSION in r.headers.cookie
        alice2 = Participant.from_id(alice.id)
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

    def sign_in(self, custom):
        data = dict(good_data)
        for k, v in custom.items():
            data['sign-in.'+k] = v
        return self.client.POST('/sign-in', data, raise_immediately=False)

    def test_sign_in(self):
        r = self.client.PxST('/sign-in', good_data)
        assert r.code == 302, r.text
        assert SESSION in r.headers.cookie
        Participant.dequeue_emails()
        assert self.get_last_email()
        p = Participant.from_username(good_data['sign-in.username'])
        assert p.avatar_url

    def test_sign_in_non_ascii_username(self):
        r = self.sign_in(dict(username='mélodie'.encode('utf8')))
        assert r.code == 400

    def test_sign_in_long_username(self):
        r = self.sign_in(dict(username='a'*200))
        assert r.code == 400

    def test_sign_in_restricted_username(self):
        r = self.sign_in(dict(username='about'))
        assert r.code == 400

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
