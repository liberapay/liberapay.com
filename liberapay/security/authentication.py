"""Defines website authentication helpers.
"""
import binascii
from datetime import date

from aspen import Response
from gratipay.models.participant import Participant
from gratipay.security import csrf
from gratipay.security.crypto import constant_time_compare
from gratipay.security.user import User, SESSION


ANON = User()

def _get_user_via_api_key(api_key):
    """Given an api_key, return a User. This auth method is deprecated.
    """
    user = User(Participant._from_thing('api_key', api_key))
    if user.participant:
        p = user.participant
        today = date.today()
        if p.old_auth_usage != today:
            Participant.db.run("""
                UPDATE participants
                   SET old_auth_usage = %s
                 WHERE id = %s
            """, (today, p.id))
    return user

def _get_user_via_basic_auth(auth_header):
    """Given a basic auth header, return a User object.
    """
    try:
        creds = binascii.a2b_base64(auth_header[len('Basic '):]).split(':', 1)
    except binascii.Error:
        raise Response(400, 'Malformed "Authorization" header')
    if len(creds) != 2:
        raise Response(401)
    userid, api_key = creds
    if len(userid) == 36 and '-' in userid:
        user = _get_user_via_api_key(userid)  # For backward-compatibility
    else:
        try:
            userid = int(userid)
        except ValueError:
            raise Response(401)
        user = User.from_id(userid)
        if user.ANON or not constant_time_compare(user.participant.api_key, api_key):
            raise Response(401)
    return user

def _turn_off_csrf(request):
    """Given a request, short-circuit CSRF.
    """
    csrf_token = csrf._get_new_token()
    request.headers.cookie['csrf_token'] = csrf_token
    request.headers['X-CSRF-TOKEN'] = csrf_token

def start_user_as_anon():
    """Make sure we always have a user object, regardless of exceptions during authentication.
    """
    return {'user': ANON}

def authenticate_user_if_possible(request, user):
    """This signs the user in.
    """
    if request.line.uri.startswith('/assets/'):
        pass
    elif 'Authorization' in request.headers:
        header = request.headers['authorization']
        if header.startswith('Basic '):
            user = _get_user_via_basic_auth(header)
            if not user.ANON:
                _turn_off_csrf(request)
    elif SESSION in request.headers.cookie:
        token = request.headers.cookie[SESSION].value
        user = User.from_session_token(token)
    return {'user': user}

def add_auth_to_response(response, request=None, user=ANON):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith('/assets/'):
        return  # assets never get auth headers

    if SESSION in request.headers.cookie:
        if not user.ANON:
            user.keep_signed_in(response.headers.cookie)
