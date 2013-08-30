"""Defines website authentication helpers.
"""
import rfc822
import time

from aspen import Response
from gittip.security import csrf
from gittip.security.user import User


BEGINNING_OF_EPOCH = rfc822.formatdate(0)
TIMEOUT = 60 * 60 * 24 * 7 # one week
ROLES = ['anonymous', 'authenticated', 'owner', 'admin']
ROLES_SHOULD_BE = "It should be one of: {}.".format(', '.join(ROLES))


class NoMinimumRoleSpecified(Exception):
    def __str__(self):
        return "There is no minimum_role specified in the simplate at {}. {}" \
               .format(self.args[0], ROLES_SHOULD_BE)

class BadMinimumRole(Exception):
    def __str__(self):
        return "The minimum_role specific in {} is bad: {}. {}" \
               .format(self.args[0], self.args[1], ROLES_SHOULD_BE)


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

    if user is None:
        user = User()
    request.context['user'] = user


def check_role(request):
    """Given a request object, possibly raise Response(403).
    """

    # XXX We can't use this yet because we don't have an inbound Aspen hook
    # that fires after the first page of the simplate is exec'd.

    context = request.context
    path = request.line.uri.path

    if 'minimum_role' not in context:
        raise NoMinimumRoleSpecified(request.fs)

    minimum_role = context['minimum_role']
    if minimum_role not in ROLES:
        raise BadMinimumRole(request.fs, minimum_role)

    user = context['user']
    highest_role = user.get_highest_role(path.get('username', None))
    if ROLES.index(highest_role) < ROLES.index(minimum_role):
        request.redirect('..')


def outbound(response):
    if 'user' in response.request.context:
        user = response.request.context['user']
        if not isinstance(user, User):
            raise Response(400, "If you define 'user' in a simplate it has to "
                                "be a User instance.")
    else:
        user = User()

    if user.ANON: # user is anonymous
        if 'session' not in response.request.headers.cookie:
            # no cookie in the request, don't set one on response
            return
        else:
            # expired cookie in the request, instruct browser to delete it
            response.headers.cookie['session'] = ''
            expires = 0
    else: # user is authenticated
        response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache
        response.headers.cookie['session'] = user.participant.session_token
        expires = time.time() + TIMEOUT
        user.keep_signed_in_until(expires)

    cookie = response.headers.cookie['session']
    # I am not setting domain, because it is supposed to default to what we
    # want: the domain of the object requested.
    #cookie['domain']
    cookie['path'] = '/'
    cookie['expires'] = rfc822.formatdate(expires)
    cookie['httponly'] = "Yes, please."
