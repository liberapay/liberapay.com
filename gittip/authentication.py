"""Defines website authentication helpers.
"""
import datetime
import rfc822
import time
import uuid

from aspen import Response
from aspen.utils import typecheck
from sqlalchemy.engine.base import RowProxy
from gittip.orm.tables import participants
from gittip.participant import Participant
from psycopg2.extras import RealDictRow


BEGINNING_OF_EPOCH = rfc822.formatdate(0)
TIMEOUT = 60 * 60 * 24 * 7 # one week


class User(Participant):
    """Represent a website user.

    Every current website user is also a participant, though if the user is
    anonymous then the methods from Participant will fail with NoParticipantId.

    """

    def __init__(self, session):
        """Takes a dict of user info.
        """
        typecheck(session, (RealDictRow, RowProxy, dict))
        self.session = dict(session)
        Participant.__init__(self, self.session.get('id'))  # sets self.id

    @classmethod
    def from_session_token(cls, token):
        user = participants.select().where(
            participants.c.session_token == token,
        ).where(
            participants.c.is_suspicious.isnot(True),
        ).execute().fetchone()
        return cls(user)

    @classmethod
    def from_id(cls, participant_id):
        user = participants.select().where(
            participants.c.id == participant_id,
        ).where(
            participants.c.is_suspicious.isnot(True),
        ).execute().fetchone()
        session = dict(user)
        session['session_token'] = uuid.uuid4().hex
        participants.update().where(
            participants.c.id == participant_id
        ).values(
            session_token = session['session_token'],
        ).execute()
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


def inbound(request):
    """Authenticate from a cookie.
    """
    if 'session' in request.headers.cookie:
        token = request.headers.cookie['session'].value
        user = User.from_session_token(token)
    else:
        user = User({})
    request.context['user'] = user


def outbound(response):
    from gittip import db
    session = {}
    if 'user' in response.request.context:
        user = response.request.context['user']
        if not isinstance(user, User):
            raise Response(400, "If you define 'user' in a simplate it has to "
                                "be a User instance.")
        session = user.session
    if not session:                                 # user is anonymous
        if 'session' not in response.request.headers.cookie:
            # no cookie in the request, don't set one on response
            return
        else:
            # expired cookie in the request, instruct browser to delete it
            response.headers.cookie['session'] = ''
            expires = 0
    else:                                           # user is authenticated
        response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache
        response.headers.cookie['session'] = session['session_token']
        expires = session['session_expires'] = time.time() + TIMEOUT
        SQL = """
            UPDATE participants SET session_expires=%s WHERE session_token=%s
        """
        db.execute( SQL
                  , ( datetime.datetime.fromtimestamp(expires)
                    , session['session_token']
                     )
                   )

    cookie = response.headers.cookie['session']
    # I am not setting domain, because it is supposed to default to what we
    # want: the domain of the object requested.
    #cookie['domain']
    cookie['path'] = '/'
    cookie['expires'] = rfc822.formatdate(expires)
    cookie['httponly'] = "Yes, please."
