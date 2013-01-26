from gittip.models.user import User
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
        alice = User.from_id('alice')
        assert not alice.ANON

    def test_known_user_is_not_admin(self):
        self.make_participant('alice')
        alice = User.from_id('alice')
        assert not alice.ADMIN

    def test_admin_user_is_admin(self):
        self.make_participant('alice', is_admin=True)
        alice = User.from_id('alice')
        assert alice.ADMIN

    def test_user_from_bad_token_is_anonymous(self):
        user = User.from_session_token('deadbeef')
        assert user.ANON

    def test_user_from_bad_id_is_anonymous(self):
        user = User.from_id('deadbeef')
        assert user.ANON

    def test_suspicious_user_from_id_is_anonymous(self):
        self.make_participant('alice', is_suspicious=True)
        user = User.from_id('alice')
        assert user.ANON

    def test_user_can_be_loaded_from_session_token(self):
        self.make_participant('alice')
        token = User.from_id('alice').session_token
        actual = User.from_session_token(token).id
        assert actual == 'alice', actual

    def test_signed_out_user_is_anonymous(self):
        self.make_participant('alice')
        alice = User.from_id('alice')
        assert not alice.ANON
        alice = alice.sign_out()
        assert alice.ANON


