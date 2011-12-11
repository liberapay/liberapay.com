import logging
import rfc822
import time
import uuid
from hashlib import sha1

from aspen import Response


log = logging.getLogger('logstown.authentication')
sessions = {}
BEGINNING_OF_EPOCH = rfc822.formatdate(0)
TIMEOUT = 60 * 60 * 24 * 7 # one week

# XXX We have users using this salt, but really it should be stronger, and
# not stored in code. Idea: add a second salt, and mark in the db whether to
# use both salts for a given user. Or ask existing users to change their 
# password.
salt = "cheese and crackers" 

def hash(password):
    return sha1(password + salt).hexdigest()

def authentic(email, password):
    from logstown import db
    SQL = ("SELECT email FROM users WHERE email=%s AND hash=%s")
    hashed = hash(password)
    rec = db.fetchone(SQL, (email, hashed))
    return rec is not None

def sign_in(email, password):
    from logstown import db
    SQL = ("UPDATE users SET session_token=%s "
           "WHERE email=%s AND hash=%s RETURNING *")
    token = str(uuid.uuid4())
    hashed = hash(password)
    rec = db.fetchone(SQL, (token, email, hashed))
    if rec is not None:
        del rec['hash'] # safety
        return rec
    return {}

def load_session(token):
    from logstown import db
    SQL = """\
        SELECT email, session_token, session_expires, payment_method_token 
          FROM users
         WHERE session_token=%s
    """
    rec = db.fetchone(SQL, (token,))
    if rec is not None:
        assert rec['session_token'] == token # sanity
        assert 'hash' not in rec # safety
        return rec
    return {}

class User:

    def __init__(self, session):
        """Takes a dict of user info.
        """
        self.session = session

    def __str__(self):
        return '<User: %s>' % getattr(self, 'email', 'Anonymous')

    @property
    def ANON(self):
        return bool(self.session.get('email', False))

def inbound(request):
    """Authenticate from a cookie.
    """
    session = {}
    if 'session' in request.cookie:
        token = request.cookie['session'].value
        session = load_session(token)
    request.user = User(session)

def outbound(response):
    session = {}
    if hasattr(response.request, 'user'):
        session = response.request.user.session
    if not session:                                 # user is anonymous
        if 'session' not in response.request.cookie:
            # no cookie in the request, don't set one on response
            return
        else:
            # expired cookie in the request, instruct browser to delete it
            response.cookie['session'] = '' 
            expires = 0
    else:                                           # user is authenticated
        response.headers.set('Expires', BEGINNING_OF_EPOCH) # don't cache
        response.cookie['session'] = session['session_token']
        expires = session['session_expires'] = time.time() + TIMEOUT

    cookie = response.cookie['session']
    # I am not setting domain, because it is supposed to default to what we 
    # want: the domain of the object requested.
    #cookie['domain']
    cookie['path'] = '/'
    cookie['expires'] = rfc822.formatdate(expires)
    cookie['httponly'] = "Yes, please."
