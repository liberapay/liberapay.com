import uuid

from gittip.orm import db
from gittip.models.participant import Participant


class User(Participant):
    """Represent a website user.

    Every current website user is also a participant, though if the user is
    anonymous then the methods from gittip.Participant will fail with
    NoParticipantId.

    """

    @classmethod
    def from_session_token(cls, token):

        # This used to read User.query.filter_by(session_token=token), but that
        # generates "session_token is NULL" when token is None, and we need
        # "session_token = NULL", or else we will match arbitrary users(!).
        # This is a bit of WTF from SQLAlchemy here, IMO: it dangerously opts
        # for idiomatic Python over idiomatic SQL. We fell prey, at least. :-/

        user = User.query.filter(User.session_token.op('=')(token)).first()

        if user and not user.is_suspicious:
            user = user
        else:
            user = User()
        return user

    @classmethod
    def from_username(cls, username):
        user = User.query.filter_by(username=username).first()
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
            db.session.add(self)
            db.session.commit()
        return User()

    @property
    def ADMIN(self):
        return self.username is not None and self.is_admin

    @property
    def ANON(self):
        return self.username is None

    def __unicode__(self):
        return '<User: %s>' % getattr(self, 'username', 'Anonymous')
