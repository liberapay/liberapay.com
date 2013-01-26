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
        user = User.query.filter_by(session_token=token).first()
        if user and not user.is_suspicious:
            user = user
        else:
            user = User()
        return user

    @classmethod
    def from_id(cls, user_id):
        user = User.query.filter_by(id=user_id).first()
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
        return self.id is not None and self.is_admin

    @property
    def ANON(self):
        return self.id is None

    def __unicode__(self):
        return '<User: %s>' % getattr(self, 'id', 'Anonymous')
