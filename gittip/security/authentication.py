"""Defines website authentication helpers.
"""
import rfc822
from datetime import timedelta

from aspen import Response
from aspen.utils import utcnow
from gittip.security import csrf
from gittip.security.user import User

BEGINNING_OF_EPOCH = rfc822.formatdate(0)
TIMEOUT = timedelta(days=7)

def inbound(request):
    """Authenticate from a cookie or an API key in basic auth.
    """
    user = None
    if request.line.uri.startswith('/assets/'):
        pass
    elif 'Authorization' in request.headers:
        header = request.headers['authorization']
        if header.startswith('Basic '):
            creds = header[len('Basic '):].decode('base64')
            token, ignored = creds.split(':')
            user = User.from_api_key(token)

            # We don't require CSRF if they basically authenticated.
            csrf_token = csrf._get_new_csrf_key()
            request.headers.cookie['csrf_token'] = csrf_token
            request.headers['X-CSRF-TOKEN'] = csrf_token
            if 'Referer' not in request.headers:
                request.headers['Referer'] = \
                                        'https://%s/' % csrf._get_host(request)
    elif 'session' in request.headers.cookie:
        token = request.headers.cookie['session'].value
        user = User.from_session_token(token)

    request.context['user'] = user or User()

def outbound(request, response):
    if request.line.uri.startswith('/assets/'): return

    response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache

    user = request.context.get('user') or User()
    if not isinstance(user, User):
        raise Response(500, "If you define 'user' in a simplate it has to "
                            "be a User instance.")

    if not user.ANON:
        user.keep_signed_in_until(utcnow() + TIMEOUT)
        response.set_cookie('session', user.participant.session_token, expires=TIMEOUT)
