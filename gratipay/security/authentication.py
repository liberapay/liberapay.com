"""Defines website authentication helpers.
"""
import binascii
from datetime import datetime

from aspen import Response
from aspen.utils import to_rfc822
from gratipay.security import csrf
from gratipay.security.crypto import constant_time_compare
from gratipay.security.user import User, SESSION


ANON = User()
BEGINNING_OF_EPOCH = to_rfc822(datetime(1970, 1, 1))

def get_auth_from_request(request):
    """Authenticate from a cookie or an API key in basic auth.
    """

    request.context['user'] = ANON  # Make sure we always have a user object

    if request.line.uri.startswith('/assets/'):
        return
    elif 'Authorization' in request.headers:
        header = request.headers['authorization']
        if header.startswith('Basic '):
            try:
                creds = binascii.a2b_base64(header[len('Basic '):]).split(':', 1)
            except binascii.Error:
                raise Response(400, 'Malformed "Authorization" header')
            if len(creds) != 2:
                raise Response(401)
            userid, api_key = creds
            user = request.context['user'] = User.from_id(userid)
            if user.ANON or not constant_time_compare(user.participant.api_key, api_key):
                raise Response(401)

            # We don't require CSRF if they basically authenticated.
            csrf_token = csrf._get_new_csrf_key()
            request.headers.cookie['csrf_token'] = csrf_token
            request.headers['X-CSRF-TOKEN'] = csrf_token
            if 'Referer' not in request.headers:
                request.headers['Referer'] = \
                                        'https://%s/' % csrf._get_host(request)
    elif SESSION in request.headers.cookie:
        token = request.headers.cookie[SESSION].value
        request.context['user'] = User.from_session_token(token)

def add_auth_to_response(response, request=None):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith('/assets/'):
        return  # assets never get auth headers and have their own caching done elsewhere

    response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache

    if SESSION in request.headers.cookie:
        user = request.context.get('user') or ANON
        if not user.ANON:
            user.keep_signed_in(response.headers.cookie)
