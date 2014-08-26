"""Cross Site Request Forgery middleware, borrowed from Django.

See also:

    https://github.com/django/django/blob/master/django/middleware/csrf.py
    https://docs.djangoproject.com/en/dev/ref/contrib/csrf/
    https://github.com/gratipay/gratipay.com/issues/88

"""

from datetime import timedelta
import re
import urlparse
from aspen import log_dammit


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


#from django.utils.http import same_origin
def same_origin(url1, url2):
    """
    Checks if two URLs are 'same-origin'
    """
    p1, p2 = urlparse.urlparse(url1), urlparse.urlparse(url2)
    return (p1.scheme, p1.hostname, p1.port) == (p2.scheme, p2.hostname, p2.port)


from aspen import Response
from crypto import constant_time_compare, get_random_string

REASON_NO_REFERER = "Referer checking failed - no Referer."
REASON_BAD_REFERER = "Referer checking failed - %s does not match %s."
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

def _is_secure(request):
    import gratipay
    return gratipay.canonical_scheme == 'https'

def _get_host(request):
    """Returns the HTTP host using the request headers.
    """
    return request.headers.get('X-Forwarded-Host', request.headers['Host'])



def inbound(request):
    """Given a Request object, reject it if it's a forgery.
    """
    if request.line.uri.startswith('/assets/'): return
    if request.line.uri.startswith('/callbacks/'): return

    try:
        csrf_token = _sanitize_token(request.headers.cookie['csrf_token'].value)
    except KeyError:
        csrf_token = None

    request.context['csrf_token'] = csrf_token or _get_new_csrf_key()

    # Assume that anything not defined as 'safe' by RC2616 needs protection
    if request.line.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):

        if _is_secure(request):
            # Suppose user visits http://example.com/
            # An active network attacker (man-in-the-middle, MITM) sends a
            # POST form that targets https://example.com/detonate-bomb/ and
            # submits it via JavaScript.
            #
            # The attacker will need to provide a CSRF cookie and token, but
            # that's no problem for a MITM and the session-independent
            # nonce we're using. So the MITM can circumvent the CSRF
            # protection. This is true for any HTTP connection, but anyone
            # using HTTPS expects better! For this reason, for
            # https://example.com/ we need additional protection that treats
            # http://example.com/ as completely untrusted. Under HTTPS,
            # Barth et al. found that the Referer header is missing for
            # same-domain requests in only about 0.2% of cases or less, so
            # we can use strict Referer checking.
            referer = request.headers.get('Referer')
            if referer is None:
                raise Response(403, REASON_NO_REFERER)

            good_referer = 'https://%s/' % _get_host(request)
            if not same_origin(referer, good_referer):
                reason = REASON_BAD_REFERER % (referer, good_referer)
                log_dammit(reason)
                raise Response(403, reason)

        if csrf_token is None:
            raise Response(403, REASON_NO_CSRF_COOKIE)

        # Check non-cookie token for match.
        request_csrf_token = ""
        if request.line.method == "POST":
            request_csrf_token = request.body.get('csrf_token', '')

        if request_csrf_token == "":
            # Fall back to X-CSRF-TOKEN, to make things easier for AJAX,
            # and possible for PUT/DELETE.
            request_csrf_token = request.headers.get('X-CSRF-TOKEN', '')

        if not constant_time_compare(request_csrf_token, csrf_token):
            raise Response(403, REASON_BAD_TOKEN)


def outbound(request, response):
    """Store the latest CSRF token as a cookie.
    """
    csrf_token = request.context.get('csrf_token')
    if csrf_token:
        response.set_cookie('csrf_token', csrf_token, expires=CSRF_TIMEOUT, httponly=False)

        # Content varies with the CSRF cookie, so set the Vary header.
        patch_vary_headers(response, ('Cookie',))
