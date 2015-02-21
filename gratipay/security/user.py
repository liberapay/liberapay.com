
from datetime import timedelta
import uuid

from aspen.utils import utcnow
from gratipay.models.participant import Participant
from gratipay.utils import set_cookie


SESSION = b'session'
SESSION_REFRESH = timedelta(hours=1)
SESSION_TIMEOUT = timedelta(hours=6)


class User(object):
    """Represent a user of our website.
    """

    # Constructors
    # ============

    def __init__(self, participant=None):
        self.participant = participant

    @classmethod
    def from_session_token(cls, token):
        """Find a participant based on token and return a User.
        """
        return cls(Participant.from_session_token(token))

    @classmethod
    def from_id(cls, userid):
        """Find a participant based on id and return a User.
        """
        return cls(Participant.from_id(userid))

    @classmethod
    def from_username(cls, username):
        """Find a participant based on username and return a User.
        """
        return cls(Participant.from_username(username))

    def __str__(self):
        if self.participant is None:
            out = '<Anonymous>'
        else:
            out = '<User: %s>' % self.participant.username
        return out
    __repr__ = __str__


    # Authentication Helpers
    # ======================

    def sign_in(self, cookies):
        """Start a new session for the user.
        """
        token = uuid.uuid4().hex
        expires = utcnow() + SESSION_TIMEOUT
        self.participant.update_session(token, expires)
        set_cookie(cookies, SESSION, token, expires)

    def keep_signed_in(self, cookies):
        """Extend the user's current session.
        """
        new_expires = utcnow() + SESSION_TIMEOUT
        if new_expires - self.participant.session_expires > SESSION_REFRESH:
            self.participant.set_session_expires(new_expires)
            token = self.participant.session_token
            set_cookie(cookies, SESSION, token, expires=new_expires)

    def sign_out(self, cookies):
        """End the user's current session.
        """
        self.participant.update_session(None, None)
        self.participant = None
        set_cookie(cookies, SESSION, '')


    # Roles
    # =====

    @property
    def ADMIN(self):
        return not self.ANON and self.participant.is_admin

    @property
    def ANON(self):
        return self.participant is None
