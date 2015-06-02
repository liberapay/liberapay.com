"""Defines website authentication helpers.
"""
import binascii

from aspen import Response
from liberapay.constants import SESSION
from liberapay.models.participant import Participant
from liberapay.security import csrf


class _ANON(object):
    ANON = True
    is_admin = False
    id = None
    __bool__ = __nonzero__ = lambda *a: False


ANON = _ANON()


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
        return
    if 'Authorization' in request.headers:
        header = request.headers['authorization']
        if not header.startswith('Basic '):
            raise Response(401, 'Unsupported authentication method')
        try:
            creds = binascii.a2b_base64(header[len('Basic '):]).split(':', 1)
        except binascii.Error:
            raise Response(400, 'Malformed "Authorization" header')
        participant = Participant.authenticate('id', 'password', *creds)
        if not participant:
            raise Response(401)
        _turn_off_csrf(request)
        return {'user': participant}
    elif SESSION in request.headers.cookie:
        creds = request.headers.cookie[SESSION].value.split(':', 1)
        p = Participant.authenticate('id', 'session', *creds)
        if p:
            return {'user': p}


def add_auth_to_response(response, request=None, user=ANON):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith('/assets/'):
        return  # assets never get auth headers

    if SESSION in request.headers.cookie:
        if not user.ANON:
            user.keep_signed_in(response.headers.cookie)
