import uuid

from gittip.participant import Participant


class User(object):
    """Represent a user of our website.
    """

    participant = None

    @classmethod
    def from_session_token(cls, token):
        self = cls()
        self.participant = Participant.from_session_token(token)
        return self

    @classmethod
    def from_id(cls, participant_id):
        from gittip import db
        SESSION = ("SELECT * FROM participants "
                   "WHERE is_suspicious IS NOT true "
                   "AND id=%s")
        session = cls.load_session(SESSION, participant_id)
        session['session_token'] = uuid.uuid4().hex
        db.execute( "UPDATE participants SET session_token=%s WHERE id=%s"
                  , (session['session_token'], participant_id)
                   )
        return cls(session)

    @staticmethod
    def load_session(SESSION, val):
        rec = db.fetchone(SESSION, (val,))
        out = {}
        if rec is not None:
            out = rec
        return out

    @classmethod
    def from_username(cls, username):
        user = User.query.filter_by(username_lower=username.lower()).first()
        if user is None or user.is_suspicious:
            user = User()
        else:
            user.session_token = uuid.uuid4().hex
            db.session.add(user)
            db.session.commit()
        return user

    def sign_out(self):
        token = self.session_token
        if token is not None:
            self.session_token = None
            self.db.session.add(self)
            self.db.session.commit()
        return User()


    def __str__(self):
        return '<User: %s>' % getattr(self, 'id', 'Anonymous')
    __repr__ = __str__

    def __getattr__(self, name):
        return self.session.get(name)

    @property
    def ADMIN(self):
        return not self.ANON and self.participant.is_admin

    @property
    def ANON(self):
        return self.participant is not None
