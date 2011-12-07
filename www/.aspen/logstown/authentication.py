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

salt = "cheese and crackers" # XXX
def hash(password):
    return sha1(password + salt).hexdigest()

SESSION_NEW = ("UPDATE users SET session_token=%s "
               "WHERE email=%s AND hash=%s RETURNING *")
def authenticate(email, password):
    from logstown import db
    token = str(uuid.uuid4())
    hashed = hash(password)
    rec = db.fetchone(SESSION_NEW, (token, email, hashed))
    if rec is not None:
        del rec['hash'] # safety
        return rec
    return {}

SESSION_LOAD = """\
    SELECT email, session_token, session_expires, payment_method_token 
      FROM users
     WHERE session_token=%s
"""
def load_session(token):
    from logstown import db
    rec = db.fetchone(SESSION_LOAD, (token,))
    if rec is not None:
        assert rec['session_token'] == token # sanity
        assert 'hash' not in rec # safety
        return rec
    return {}

class User:

    def __init__(self, session):
        """Takes a dict of user info.
        """
        self.__dict__.update(session)
        self.session = session

    def __str__(self):
        return '<User: %s>' % getattr(self, 'email', 'Anonymous')

def _authorize_anonymous(path):
    """Given the path part of an URL, return a boolean.
    """
    if path in ('/favicon.ico', '/robots.txt'): # special cases
        return True
    if path and path.startswith('/anonymous/'): # logging in
        return True
    return False

def inbound(request):
    """Authenticate from a cookie.
    """
    session = {}
    if 'session' in request.cookie:
        token = request.cookie['session'].value
        session = load_session(token)

    request.user = User(session)
    if not session:
        if not _authorize_anonymous(request.path.raw):
            raise Response(401) # use nice error messages for login form

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
