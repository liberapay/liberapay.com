"""Cross Site Request Forgery middleware, borrowed from Django.

See also:

    https://github.com/django/django/blob/master/django/middleware/csrf.py
    https://docs.djangoproject.com/en/dev/ref/contrib/csrf/
    https://github.com/gratipay/gratipay.com/issues/88

"""
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta
import re


#from django.utils.cache import patch_vary_headers
cc_delim_re = re.compile(r'\s*,\s*')
def patch_vary_headers(response, newheaders):
    """
    Adds (or updates) the "Vary" header in the given HttpResponse object.
    newheaders is a list of header names that should be in "Vary". Existing
    headers in "Vary" aren't removed.
    """
    # Note that we need to keep the original order intact, because cache
    # implementations may rely on the order of the Vary contents in, say,
    # computing an MD5 hash.
    if 'Vary' in response.headers:
        vary_headers = cc_delim_re.split(response.headers['Vary'])
    else:
        vary_headers = []
    # Use .lower() here so we treat headers as case-insensitive.
    existing_headers = set([header.lower() for header in vary_headers])
    additional_headers = [newheader for newheader in newheaders
                          if newheader.lower() not in existing_headers]
    response.headers['Vary'] = ', '.join(vary_headers + additional_headers)


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

    return {'csrf_token': token or _get_new_token()}


def reject_forgeries(request, csrf_token):
    # Assume that anything not defined as 'safe' by RC2616 needs protection.
    if request.line.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):

        # But for webhooks we depend on IP filtering for security.
        if request.line.uri.startswith('/callbacks/'):
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

        # Content varies with the CSRF cookie, so set the Vary header.
        patch_vary_headers(response, ('Cookie',))
