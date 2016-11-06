"""Cross Site Request Forgery middleware, originally borrowed from Django.

See also:

    https://github.com/django/django/blob/master/django/middleware/csrf.py
    https://docs.djangoproject.com/en/dev/ref/contrib/csrf/
    https://github.com/gratipay/gratipay.com/issues/88

"""
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta
import re

from .crypto import constant_time_compare, get_random_string


TOKEN_LENGTH = 32
CSRF_TOKEN = str('csrf_token')  # bytes in python2, unicode in python3
CSRF_TIMEOUT = timedelta(days=7)
SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}

_get_new_token = lambda: get_random_string(TOKEN_LENGTH)
_token_re = re.compile(r'^[a-zA-Z0-9]{%d}$' % TOKEN_LENGTH)
_sanitize_token = lambda t: t if _token_re.match(t) else None


def extract_token_from_cookie(request):
    """Given a Request object, return a csrf_token.
    """

    off = (
        # Turn off CSRF protection on assets, to avoid busting the cache.
        request.path.raw.startswith('/assets/') or
        # Turn off CSRF protection on callbacks, so they can receive POST requests.
        request.path.raw.startswith('/callbacks/') or
        # Turn off CSRF when using HTTP auth, so API users can use POST and others.
        b'Authorization' in request.headers
    )

    if off:
        token = None
    else:
        try:
            token = request.headers.cookie[CSRF_TOKEN].value
        except KeyError:
            token = _get_new_token()
        else:
            token = _sanitize_token(token) or _get_new_token()

    return {'csrf_token': token}


def reject_forgeries(request, response, csrf_token):
    if csrf_token is None:
        # CSRF protection is turned off for this request
        return

    # Assume that anything not defined as 'safe' by RFC7231 needs protection.
    if request.line.method not in SAFE_METHODS:

        # Check non-cookie token for match.
        second_token = ""
        if request.line.method == "POST":
            if isinstance(request.body, dict):
                second_token = request.body.get('csrf_token', '')

        if second_token == "":
            # Fall back to X-CSRF-TOKEN, to make things easier for AJAX,
            # and possible for PUT/DELETE.
            second_token = request.headers.get(b'X-CSRF-TOKEN', b'').decode('ascii', 'replace')

        if not constant_time_compare(second_token, csrf_token):
            raise response.error(403, "Bad CSRF cookie")


def add_token_to_response(response, csrf_token=None):
    """Store the latest CSRF token as a cookie.
    """
    if csrf_token:
        # Don't set httponly so that we can POST using XHR.
        # https://github.com/gratipay/gratipay.com/issues/3030
        response.set_cookie(CSRF_TOKEN, csrf_token, expires=CSRF_TIMEOUT, httponly=False)
