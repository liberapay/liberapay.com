# coding: utf8

from __future__ import division, print_function, unicode_literals

from liberapay.constants import SESSION
from liberapay.models.participant import Participant
from liberapay.testing.emails import EmailHarness


good_data = dict(action='sign-in', username='bob', password='password',
                 kind='individual', email='bob@example.com')


class TestSignIn(EmailHarness):

    def test_log_in(self):
        password = 'password'
        alice = self.make_participant('alice')
        alice.update_password(password)
        data = dict(action='log-in', username='alice', password=password)
        r = self.client.PxST('/sign-in', data)
        assert r.code == 302
        assert SESSION in r.headers.cookie

    def test_log_in_closed_account(self):
        password = 'password'
        alice = self.make_participant('alice')
        alice.update_password(password)
        alice.update_status('closed')
        data = dict(action='log-in', username='alice', password=password)
        r = self.client.PxST('/sign-in', data)
        assert r.code == 302
        assert SESSION in r.headers.cookie
        alice2 = Participant.from_id(alice.id)
        assert alice2.status == 'active'
        assert alice2.join_time == alice.join_time

    def test_log_in_bad_username(self):
        data = dict(action='log-in', username='alice', password='password')
        r = self.client.POST('/sign-in', data)
        assert SESSION not in r.headers.cookie

    def test_log_in_no_password(self):
        stub = self.make_stub()
        data = dict(action='log-in', username=stub.username, password='')
        r = self.client.POST('/sign-in', data)
        assert SESSION not in r.headers.cookie

    def test_log_in_bad_password(self):
        alice = self.make_participant('alice')
        alice.update_password('password')
        data = dict(action='log-in', username='alice', password='deadbeef')
        r = self.client.POST('/sign-in', data)
        assert SESSION not in r.headers.cookie

    def test_sign_in(self):
        r = self.client.PxST('/sign-in', good_data)
        assert r.code == 302, r.body
        assert SESSION in r.headers.cookie
        Participant.dequeue_emails()
        assert self.get_last_email()

    def test_sign_in_non_ascii_username(self):
        data = dict(good_data, username='mélodie'.encode('utf8'))
        r = self.client.PxST('/sign-in', data)
        assert r.code == 400

    def test_sign_in_long_username(self):
        r = self.client.PxST('/sign-in', dict(good_data, username='a'*200))
        assert r.code == 400

    def test_sign_in_restricted_username(self):
        r = self.client.PxST('/sign-in', dict(good_data, username='about'))
        assert r.code == 400

    def test_sign_in_short_password(self):
        r = self.client.PxST('/sign-in', dict(good_data, password='a'))
        assert r.code == 400

    def test_sign_in_long_password(self):
        r = self.client.PxST('/sign-in', dict(good_data, password='a'*200))
        assert r.code == 400

    def test_sign_in_bad_kind(self):
        r = self.client.PxST('/sign-in', dict(good_data, kind='group'))
        assert r.code == 400
