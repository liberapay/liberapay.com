from aspen.utils import typecheck


class Visitor(object):
    """Represent a website visitor.
    """

    def __init__(self, session):
        """Takes a dict of user info.
        """
        typecheck(session, (RealDictRow, dict))
        self.session = session
        Participant.__init__(self, session.get('id'))  # sets self.id

    @classmethod
    def from_session_token(cls, token):
        SESSION = ("SELECT * FROM participants "
                   "WHERE is_suspicious IS NOT true "
                   "AND session_token=%s")
        session = cls.load_session(SESSION, token)
        return cls(session)

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
        from gittip import db
        rec = db.fetchone(SESSION, (val,))
        out = {}
        if rec is not None:
            out = rec
        return out

    def __str__(self):
        return '<User: %s>' % getattr(self, 'id', 'Anonymous')
    __repr__ = __str__

    def __getattr__(self, name):
        return self.session.get(name)

    @property
    def ADMIN(self):
        return bool(self.session.get('is_admin', False))

    @property
    def ANON(self):
        return self.id is None

