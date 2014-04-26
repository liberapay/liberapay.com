"""Defines website authentication helpers.
"""
import rfc822
import time

import gittip
from aspen import Response
from gittip.security import csrf
from gittip.security.user import User

BEGINNING_OF_EPOCH = rfc822.formatdate(0)
TIMEOUT = 60 * 60 * 24 * 7 # one week

def inbound(request):
    """Authenticate from a cookie or an API key in basic auth.
    """
    user = None
    if 'Authorization' in request.headers:
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
    if 'user' in request.context:
        user = request.context['user']
        if not isinstance(user, User):
            raise Response(400, "If you define 'user' in a simplate it has to "
                                "be a User instance.")

        response.headers.cookie['session'] = user.participant.session_token
        expires = time.time() + TIMEOUT
        user.keep_signed_in_until(expires)
    elif 'session' in request.headers.cookie:
        response.headers.cookie['session'] = ''
        expires = 0
    else: return

    response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache

    cookie = response.headers.cookie['session']
    cookie['path'] = '/'
    cookie['expires'] = rfc822.formatdate(expires)
    cookie['httponly'] = "Yes, please."
    if gittip.canonical_scheme == 'https':
        cookie['secure'] = "Yes, please."
