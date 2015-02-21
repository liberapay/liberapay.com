"""Defines website authentication helpers.
"""
import binascii
from datetime import date, datetime

from aspen import Response
from aspen.utils import to_rfc822
from gratipay.models.participant import Participant
from gratipay.security import csrf
from gratipay.security.crypto import constant_time_compare
from gratipay.security.user import User, SESSION


ANON = User()
BEGINNING_OF_EPOCH = to_rfc822(datetime(1970, 1, 1))

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
    csrf_token = csrf._get_new_csrf_key()
    request.headers.cookie['csrf_token'] = csrf_token
    request.headers['X-CSRF-TOKEN'] = csrf_token

def set_request_context_user(request):
    """Set request.context['user']. This signs the user in.
    """

    request.context['user'] = user = ANON  # Make sure we always have a user object, even if
                                           # there's an exception in the rest of this function.

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

    request.context['user'] = user

def add_auth_to_response(response, request=None):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith('/assets/'):
        return  # assets never get auth headers and have their own caching done elsewhere

    response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache

    if SESSION in request.headers.cookie:
        user = request.context.get('user') or ANON
        if not user.ANON:
            user.keep_signed_in(response.headers.cookie)
