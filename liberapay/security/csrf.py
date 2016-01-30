"""Cross Site Request Forgery middleware, borrowed from Django.

See also:

    https://github.com/django/django/blob/master/django/middleware/csrf.py
    https://docs.djangoproject.com/en/dev/ref/contrib/csrf/
    https://github.com/gratipay/gratipay.com/issues/88

"""
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta
import re

from aspen import Response

from .crypto import constant_time_compare, get_random_string


TOKEN_LENGTH = 32
CSRF_TIMEOUT = timedelta(days=7)

_get_new_token = lambda: get_random_string(TOKEN_LENGTH).encode('ascii')
_token_re = re.compile(r'^[a-zA-Z0-9]{%d}$' % TOKEN_LENGTH)
_sanitize_token = lambda t: t if _token_re.match(t) else None


def extract_token_from_cookie(request):
    """Given a Request object, return a csrf_token.
    """
    try:
        token = request.headers.cookie['csrf_token'].value
    except KeyError:
        token = None
    else:
        token = _sanitize_token(token)

    # Don't set a CSRF cookie on assets, to avoid busting the cache.
    # Don't set it on callbacks, because we don't need it there.

    if request.path.raw.startswith('/assets/') or request.path.raw.startswith('/callbacks/'):
        token = None
    else:
        token = token or _get_new_token()

    return {'csrf_token': token}


def reject_forgeries(request, csrf_token):
    # Assume that anything not defined as 'safe' by RC2616 needs protection.
    if request.line.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):

        # except webhooks
        if request.line.uri.startswith('/callbacks/'):
            return
        # and requests using HTTP auth
        if 'Authorization' in request.headers:
            return

        # Check non-cookie token for match.
        second_token = ""
        if request.line.method == "POST":
            if isinstance(request.body, dict):
                second_token = request.body.get('csrf_token', '')

        if second_token == "":
            # Fall back to X-CSRF-TOKEN, to make things easier for AJAX,
            # and possible for PUT/DELETE.
            second_token = request.headers.get('X-CSRF-TOKEN', '')

        if not constant_time_compare(second_token, csrf_token):
            raise Response(403, "Bad CSRF cookie")


def add_token_to_response(response, csrf_token=None):
    """Store the latest CSRF token as a cookie.
    """
    if csrf_token:
        # Don't set httponly so that we can POST using XHR.
        # https://github.com/gratipay/gratipay.com/issues/3030
        response.set_cookie(b'csrf_token', csrf_token, expires=CSRF_TIMEOUT, httponly=False)
