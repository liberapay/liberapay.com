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
    def from_api_key(cls, api_key):
        """Find a participant based on token and return a User.
        """
        self = cls()
        self.participant = Participant.from_api_key(api_key)
        return self

    @classmethod
    def from_username(cls, username):
        """Find a participant based on username and return a User.
        """
        self = cls()
        self.participant = Participant.from_username(username)
        return self

    def __str__(self):
        if self.participant is None:
            out = '<Anonymous>'
        else:
            out = '<User: %s>' % self.participant.username
        return out
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


    # Roles
    # =====

    @property
    def ADMIN(self):
        return not self.ANON and self.participant.is_admin

    @property
    def ANON(self):
        return self.participant is None or self.participant.is_suspicious is True
        # Append "is True" here because otherwise Python will return the result
        # of evaluating the right side of the or expression, which can be None.

    def get_highest_role(self, owner):
        """Return a string representing the highest role this user has.

        :param string owner: the username of the owner of the resource we're
            concerned with, or None

        """
        def is_owner():
            if self.participant is not None:
                if owner is not None:
                    if self.participant.username == owner:
                        return True
            return False

        if self.ADMIN:
            return 'admin'
        elif is_owner():
            return 'owner'
        elif not self.ANON:
            return 'authenticated'
        else:
            return 'anonymous'
