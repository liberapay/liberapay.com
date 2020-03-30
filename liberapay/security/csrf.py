"""Cross Site Request Forgery middleware, originally borrowed from Django.

See also:

    https://github.com/django/django/blob/master/django/middleware/csrf.py
    https://docs.djangoproject.com/en/dev/ref/contrib/csrf/
    https://github.com/gratipay/gratipay.com/issues/88

"""

from datetime import timedelta

from pando.exceptions import UnknownBodyType

from ..constants import SAFE_METHODS
from .crypto import constant_time_compare, get_random_string


TOKEN_LENGTH = 32
CSRF_TOKEN = 'csrf_token'
CSRF_TIMEOUT = timedelta(days=7)


class CSRF_Token:
    """A lazy anti-CSRF token generator.
    """

    __slots__ = ('state', '_token')

    def __init__(self, state):
        self.state = state
        self._token = None

    def __bool__(self):
        return bool(self._token)

    def __eq__(self, other):
        return self._token == other

    def __ne__(self, other):
        return self._token != other

    def __repr__(self):
        return f"<CSRF_Token _token={self._token!r}>"

    def __str__(self):
        return self.token

    @property
    def token(self):
        if not self._token:
            try:
                cookie_token = self.state['request'].headers.cookie[CSRF_TOKEN].value
            except KeyError:
                cookie_token = ''
            if len(cookie_token) == TOKEN_LENGTH:
                self._token = cookie_token
            else:
                self._token = get_random_string(TOKEN_LENGTH)
        return self._token


def add_csrf_token_to_state(state):
    state['csrf_token'] = CSRF_Token(state)


def reject_forgeries(state, request, response, website, _):
    request_path = request.path.raw
    off = (
        # Assume that methods defined as 'safe' by RFC7231 don't need protection.
        request.method in SAFE_METHODS or
        # Don't check CSRF tokens for callbacks, it's not necessary.
        request_path.startswith('/callbacks/') or
        # CSRF protection is turned off for this request.
        request_path == '/migrate' and not request.qs
    )
    if off:
        return

    # Get token from cookies.
    try:
        cookie_token = request.headers.cookie[CSRF_TOKEN].value
    except KeyError:
        raise response.error(403, _(
            "A security check has failed. Please make sure your browser is "
            "configured to allow cookies for {domain}, then try again.",
            domain=website.canonical_host
        ))

    # Check non-cookie token for match.
    second_token = ""
    if request.method == "POST":
        try:
            if isinstance(request.body, dict):
                second_token = request.body.get('csrf_token', '')
        except UnknownBodyType:
            pass

    if second_token == "":
        # Fall back to X-CSRF-TOKEN, to make things easier for AJAX,
        # and possible for PUT/DELETE.
        second_token = request.headers.get(b'X-CSRF-TOKEN', b'').decode('ascii', 'replace')
        if not second_token:
            raise response.error(403, "The X-CSRF-TOKEN header is missing.")

    if not constant_time_compare(second_token, cookie_token):
        raise response.error(403, "The anti-CSRF tokens don't match.")


def add_token_to_response(response, csrf_token=None):
    """Store the latest CSRF token as a cookie.
    """
    if csrf_token:
        # Don't set httponly so that we can POST using XHR.
        # https://github.com/gratipay/gratipay.com/issues/3030
        response.set_cookie(CSRF_TOKEN, str(csrf_token), expires=CSRF_TIMEOUT, httponly=False)
