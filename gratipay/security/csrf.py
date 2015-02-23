"""Cross Site Request Forgery middleware, borrowed from Django.

See also:

    https://github.com/django/django/blob/master/django/middleware/csrf.py
    https://docs.djangoproject.com/en/dev/ref/contrib/csrf/
    https://github.com/gratipay/gratipay.com/issues/88

"""

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
from crypto import constant_time_compare, get_random_string

REASON_NO_CSRF_COOKIE = "CSRF cookie not set."
REASON_BAD_TOKEN = "CSRF token missing or incorrect."

TOKEN_LENGTH = 32
CSRF_TIMEOUT = timedelta(days=7)


def _get_new_csrf_key():
    return get_random_string(TOKEN_LENGTH)


def _sanitize_token(token):
    # Allow only alphanum, and ensure we return a 'str' for the sake
    # of the post processing middleware.
    if len(token) > TOKEN_LENGTH:
        return _get_new_csrf_key()
    token = re.sub('[^a-zA-Z0-9]+', '', str(token.decode('ascii', 'ignore')))
    if token == "":
        # In case the cookie has been truncated to nothing at some point.
        return _get_new_csrf_key()
    return token



def get_csrf_token_from_request(request, state):
    """Given a Request object, reject it if it's a forgery.
    """
    if request.line.uri.startswith('/assets/'): return
    if request.line.uri.startswith('/callbacks/'): return

    try:
        csrf_token = _sanitize_token(request.headers.cookie['csrf_token'].value)
    except KeyError:
        csrf_token = None

    state['csrf_token'] = csrf_token or _get_new_csrf_key()

    # Assume that anything not defined as 'safe' by RC2616 needs protection
    if request.line.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):

        if csrf_token is None:
            raise Response(403, REASON_NO_CSRF_COOKIE)

        # Check non-cookie token for match.
        request_csrf_token = ""
        if request.line.method == "POST":
            if isinstance(request.body, dict):
                request_csrf_token = request.body.get('csrf_token', '')

        if request_csrf_token == "":
            # Fall back to X-CSRF-TOKEN, to make things easier for AJAX,
            # and possible for PUT/DELETE.
            request_csrf_token = request.headers.get('X-CSRF-TOKEN', '')

        if not constant_time_compare(request_csrf_token, csrf_token):
            raise Response(403, REASON_BAD_TOKEN)


def add_csrf_token_to_response(response, csrf_token=None):
    """Store the latest CSRF token as a cookie.
    """
    if csrf_token:
        # Don't set httponly so that we can POST using XHR.
        # https://github.com/gratipay/gratipay.com/issues/3030
        response.set_cookie('csrf_token', csrf_token, expires=CSRF_TIMEOUT, httponly=False)

        # Content varies with the CSRF cookie, so set the Vary header.
        patch_vary_headers(response, ('Cookie',))
