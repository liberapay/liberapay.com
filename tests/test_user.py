from __future__ import print_function, unicode_literals

from gittip.security.user import User
from gittip.testing import Harness


class TestUser(Harness):

    def test_anonymous_user_is_anonymous(self):
        user = User()
        assert user.ANON

    def test_anonymous_user_is_not_admin(self):
        user = User()
        assert not user.ADMIN

    def test_known_user_is_known(self):
        self.make_participant('alice')
        alice = User.from_username('alice')
        assert not alice.ANON

    def test_username_is_case_insensitive(self):
        self.make_participant('AlIcE')
        actual = User.from_username('aLiCe').participant.username_lower
        assert actual == 'alice', actual

    def test_known_user_is_not_admin(self):
        self.make_participant('alice')
        alice = User.from_username('alice')
        assert not alice.ADMIN

    def test_admin_user_is_admin(self):
        self.make_participant('alice', is_admin=True)
        alice = User.from_username('alice')
        assert alice.ADMIN


    # ANON

    def test_unreviewed_user_is_not_ANON(self):
        self.make_participant('alice', is_suspicious=None)
        alice = User.from_username('alice')
        assert alice.ANON is False

    def test_whitelisted_user_is_not_ANON(self):
        self.make_participant('alice', is_suspicious=False)
        alice = User.from_username('alice')
        assert alice.ANON is False

    def test_blacklisted_user_is_ANON(self):
        self.make_participant('alice', is_suspicious=True)
        alice = User.from_username('alice')
        assert alice.ANON is True


    # session token

    def test_user_from_bad_session_token_is_anonymous(self):
        user = User.from_session_token('deadbeef')
        assert user.ANON

    def test_user_from_None_session_token_is_anonymous(self):
        self.make_participant('alice')
        self.make_participant('bob')
        user = User.from_session_token(None)
        assert user.ANON

    def test_user_can_be_loaded_from_session_token(self):
        self.make_participant('alice')
        user = User.from_username('alice')
        user.sign_in()
        token = user.participant.session_token
        actual = User.from_session_token(token).participant.username
        assert actual == 'alice', actual


    # key token

    def test_user_from_bad_api_key_is_anonymous(self):
        user = User.from_api_key('deadbeef')
        assert user.ANON

    def test_user_from_None_api_key_is_anonymous(self):
        self.make_participant('alice')
        self.make_participant('bob')
        user = User.from_api_key(None)
        assert user.ANON

    def test_user_can_be_loaded_from_api_key(self):
        alice = self.make_participant('alice')
        api_key = alice.recreate_api_key()
        actual = User.from_api_key(api_key).participant.username
        assert actual == 'alice', actual


    def test_user_from_bad_id_is_anonymous(self):
        user = User.from_username('deadbeef')
        assert user.ANON

    def test_suspicious_user_from_username_is_anonymous(self):
        self.make_participant('alice', is_suspicious=True)
        user = User.from_username('alice')
        assert user.ANON

    def test_signed_out_user_is_anonymous(self):
        self.make_participant('alice')
        alice = User.from_username('alice')
        assert not alice.ANON
        alice.sign_out()
        assert alice.ANON
