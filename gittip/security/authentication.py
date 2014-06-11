"""Defines website authentication helpers.
"""
from datetime import datetime

from gittip.utils import to_rfc822
from gittip.security import csrf
from gittip.security.user import User, SESSION

BEGINNING_OF_EPOCH = to_rfc822(datetime(1970, 1, 1))

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
    elif SESSION in request.headers.cookie:
        token = request.headers.cookie[SESSION].value
        user = User.from_session_token(token)

    request.context['user'] = user or User()

def outbound(request, response):
    if request.line.uri.startswith('/assets/'): return

    response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache

    if SESSION in request.headers.cookie:
        user = request.context.get('user') or User()
        if not user.ANON:
            user.keep_signed_in(response.headers.cookie)
