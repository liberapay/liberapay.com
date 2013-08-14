from gittip.models.participant import Participant


class User(object):
    """Represent a user of our website.
    """

    participant = None


    # Constructors
    # ============

    @classmethod
    def from_session_token(cls, token):
        """Find a participant based on token and return a User.
        """
        self = cls()
        self.participant = Participant.from_session_token(token)
        return self

    @classmethod
    def from_username(cls, username):
        """Find a participant based on username and return a User.
        """
        self = cls()
        self.participant = Participant.from_id(username)
        return self

    def __str__(self):
        return '<User: %s>' % getattr(self, 'id', 'Anonymous')
    __repr__ = __str__


    # Authentication Helpers
    # ======================

    def sign_in(self):
        """Start a new session for the user.
        """
        self.participant.start_new_session()

    def keep_signed_in_until(self, expires):
        """Extend the user's current session.

        :param float expires: A UNIX timestamp (XXX timezone?)

        """
        self.participant.set_session_expires(expires)

    def sign_out(self):
        """End the user's current session.
        """
        self.participant.end_session()
        self.participant = None


    # Role Booleans
    # =============

    @property
    def ADMIN(self):
        return not self.ANON and self.participant.is_admin

    @property
    def ANON(self):
        return self.participant is None
