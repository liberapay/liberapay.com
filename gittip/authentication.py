"""Defines website authentication helpers.
"""
import datetime
import rfc822
import time

import pytz
from aspen import Response
from gittip.orm import db
from gittip.models import User


BEGINNING_OF_EPOCH = rfc822.formatdate(0)
TIMEOUT = 60 * 60 * 24 * 7 # one week


def inbound(request):
    """Authenticate from a cookie.
    """
    if 'session' in request.headers.cookie:
        token = request.headers.cookie['session'].value
        user = User.from_session_token(token)
    else:
        user = User()
    request.context['user'] = user


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
        user = User.from_session_token(user.session_token)
        response.headers['Expires'] = BEGINNING_OF_EPOCH # don't cache
        response.headers.cookie['session'] = user.session_token
        expires = time.time() + TIMEOUT
        user.session_expires = datetime.datetime.fromtimestamp(expires)\
                                                .replace(tzinfo=pytz.utc)
        db.session.add(user)
        db.session.commit()

    cookie = response.headers.cookie['session']
    # I am not setting domain, because it is supposed to default to what we
    # want: the domain of the object requested.
    #cookie['domain']
    cookie['path'] = '/'
    cookie['expires'] = rfc822.formatdate(expires)
    cookie['httponly'] = "Yes, please."
