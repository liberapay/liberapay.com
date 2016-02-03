"""This subpackage contains functionality for working with accounts elsewhere.
"""
from __future__ import division, print_function, unicode_literals

from collections import OrderedDict
from datetime import datetime
import hashlib
import json
import logging
try:
    from urllib.parse import quote
except ImportError:
    from urllib import quote
import xml.etree.ElementTree as ET

from aspen import log, Response
from aspen.utils import to_age, utc
from oauthlib.oauth2 import TokenExpiredError
from requests_oauthlib import OAuth1Session, OAuth2Session

from liberapay.elsewhere._extractors import not_available
from liberapay.exceptions import LazyResponse


ACTIONS = {'connect', 'lock', 'unlock'}


class UnknownAccountElsewhere(Exception): pass


class PlatformRegistry(object):
    """Registry of platforms we support.
    """
    def __init__(self, platforms):
        self.__dict__ = OrderedDict((p.name, p) for p in platforms)

    def __contains__(self, platform):
        return platform.name in self.__dict__

    def __iter__(self):
        return iter(self.__dict__.values())


class UserInfo(object):
    """A simple container for a user's info.

    Accessing a non-existing attribute returns `None`.
    """

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, key):
        return self.__dict__.get(key, None)

    def __setattr__(self, key, value):
        if value is None:
            self.__dict__.pop(key, None)
        else:
            self.__dict__[key] = value


class Platform(object):

    allows_team_connect = False

    # "x" stands for "extract"
    x_user_info = not_available
    x_user_id = not_available
    x_user_name = not_available
    x_display_name = not_available
    x_email = not_available
    x_gravatar_id = not_available
    x_avatar_url = not_available
    x_is_team = not_available

    required_attrs = ( 'account_url'
                     , 'display_name'
                     , 'name'
                     )

    def __init__(self, api_key, api_secret, callback_url, api_url=None, auth_url=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.callback_url = callback_url
        if api_url:
            self.api_url = api_url
        if auth_url:
            self.auth_url = auth_url
        elif not getattr(self, 'auth_url', None):
            self.auth_url = self.api_url

        # Determine the appropriate response parser using `self.api_format`
        api_format = getattr(self, 'api_format', None)
        if api_format == 'json':
            self.api_parser = lambda r: r.json()
        elif api_format == 'xml':
            self.api_parser = lambda r: ET.fromstring(r.content)
        elif api_format:
            raise ValueError('unknown API format: '+str(api_format))

        # Make sure the subclass was implemented properly.
        missing_attrs = [a for a in self.required_attrs if not hasattr(self, a)]
        if missing_attrs:
            msg = "The class %s is missing these required attributes: %s"
            msg %= self.__class__.__name__, ', '.join(missing_attrs)
            raise AttributeError(msg)

    def api_get(self, path, sess=None, **kw):
        """
        Given a `path` (e.g. /users/foo), this function sends a GET request to
        the platform's API (e.g. https://api.github.com/users/foo).

        The response is returned, after checking its status code and ratelimit
        headers.
        """
        url = self.api_url+path
        is_user_session = bool(sess)
        if not sess:
            sess = self.get_auth_session()
            if self.name == 'github':
                url += '?' if '?' not in url else '&'
                url += 'client_id=%s&client_secret=%s' % (self.api_key, self.api_secret)
        response = sess.get(url, **kw)

        limit, remaining, reset = self.get_ratelimit_headers(response)
        if not is_user_session:
            self.log_ratelimit_headers(limit, remaining, reset)

        # Check response status
        status = response.status_code
        if status == 401 and isinstance(self, PlatformOAuth1):
            # https://tools.ietf.org/html/rfc5849#section-3.2
            if is_user_session:
                raise TokenExpiredError
            raise Response(500)
        if status == 404:
            raise Response(404, response.text)
        if status == 429 and is_user_session:
            def msg(_, to_age):
                if remaining == 0 and reset:
                    return _("You've consumed your quota of requests, you can try again in {0}.", to_age(reset))
                else:
                    return _("You're making requests too fast, please try again later.")
            raise LazyResponse(status, msg)
        if status != 200:
            log('{} api responded with {}:\n{}'.format(self.name, status, response.text)
               , level=logging.ERROR)
            msg = lambda _: _("{0} returned an error, please try again later.",
                              self.display_name)
            raise LazyResponse(502, msg)

        return response

    def get_ratelimit_headers(self, response):
        limit, remaining, reset = None, None, None
        prefix = getattr(self, 'ratelimit_headers_prefix', None)
        if prefix:
            limit = response.headers.get(prefix+'limit')
            remaining = response.headers.get(prefix+'remaining')
            reset = response.headers.get(prefix+'reset')

            try:
                limit, remaining, reset = int(limit), int(remaining), int(reset)
                reset = datetime.fromtimestamp(reset, tz=utc)
            except (TypeError, ValueError):
                d = dict(limit=limit, remaining=remaining, reset=reset)
                log('Got weird rate headers from %s: %s' % (self.name, d))
                limit, remaining, reset = None, None, None

        return limit, remaining, reset

    def log_ratelimit_headers(self, limit, remaining, reset):
        """Emit log messages if we're running out of ratelimit.
        """
        if None in (limit, remaining, reset):
            return
        percent_remaining = remaining/limit
        if percent_remaining < 0.5:
            log_msg = (
                '{0} API: {1:.1%} of ratelimit has been consumed, '
                '{2} requests remaining, resets {3}.'
            ).format(self.name, 1 - percent_remaining, remaining, to_age(reset))
            log_lvl = logging.WARNING
            if percent_remaining < 0.2:
                log_lvl = logging.ERROR
            elif percent_remaining < 0.05:
                log_lvl = logging.CRITICAL
            log(log_msg, log_lvl)

    def extract_user_info(self, info):
        """
        Given a user_info object of variable type (depending on the platform),
        extract the relevant information by calling the platform's extractors
        (`x_user_name`, `x_user_id`, etc).

        Returns a `UserInfo`. The `user_id` attribute is guaranteed to have a
        unique non-empty value.
        """
        r = UserInfo(platform=self.name)
        info = self.x_user_info(r, info, info)
        r.user_name = self.x_user_name(r, info, None)
        if self.x_user_id.__func__ is not_available:
            r.user_id = r.user_name
        else:
            r.user_id = self.x_user_id(r, info)
        assert r.user_id is not None
        r.user_id = str(r.user_id)
        assert len(r.user_id) > 0
        r.display_name = self.x_display_name(r, info, None)
        r.email = self.x_email(r, info, None)
        r.avatar_url = self.x_avatar_url(r, info, None)
        if not r.avatar_url:
            gravatar_id = self.x_gravatar_id(r, info, None)
            if r.email and not gravatar_id:
                gravatar_id = hashlib.md5(r.email.strip().lower()).hexdigest()
            if gravatar_id:
                r.avatar_url = 'https://secure.gravatar.com/avatar/'+gravatar_id
        r.is_team = self.x_is_team(r, info, False)
        r.extra_info = info
        return r

    def get_team_members(self, account, page_url=None):
        """Given an AccountElsewhere, return its membership list from the API.
        """
        if not page_url:
            page_url = self.api_team_members_path.format(
                user_id=quote(account.user_id),
                user_name=quote(account.user_name or ''),
            )
        r = self.api_get(page_url)
        members, count, pages_urls = self.api_paginator(r, self.api_parser(r))
        members = [self.extract_user_info(m) for m in members]
        return members, count, pages_urls

    def get_user_info(self, key, value, sess=None):
        """Given a user_name or user_id, get the user's info from the API.
        """
        if key == 'user_id':
            path = 'api_user_info_path'
        else:
            assert key == 'user_name'
            path = 'api_user_name_info_path'
        path = getattr(self, path, None)
        if not path:
            raise Response(400)
        path = path.format(**{key: value})
        info = self.api_parser(self.api_get(path, sess=sess))
        return self.extract_user_info(info)

    def get_user_self_info(self, sess):
        """Get the authenticated user's info from the API.
        """
        r = self.api_get(self.api_user_self_info_path, sess=sess)
        info = self.extract_user_info(self.api_parser(r))
        token = getattr(sess, 'token', None)
        if token:
            info.token = json.dumps(token)
        return info

    def get_friends_for(self, account, page_url=None, sess=None):
        if not page_url:
            page_url = self.api_friends_path.format(
                user_id=quote(account.user_id),
                user_name=quote(account.user_name or ''),
            )
        r = self.api_get(page_url, sess=sess)
        friends, count, pages_urls = self.api_paginator(r, self.api_parser(r))
        friends = [self.extract_user_info(f) for f in friends]
        if count == -1 and hasattr(self, 'x_friends_count'):
            count = self.x_friends_count(None, account.extra_info, -1)
        return friends, count, pages_urls


class PlatformOAuth1(Platform):

    request_token_path = '/oauth/request_token'
    authorize_path = '/oauth/authorize'
    access_token_path = '/oauth/access_token'

    def get_auth_session(self, token=None):
        args = ()
        if token:
            args = (token['token'], token['token_secret'])
        return OAuth1Session(self.api_key, self.api_secret, *args,
                             callback_uri=self.callback_url)

    def get_auth_url(self, **kw):
        sess = self.get_auth_session()
        r = sess.fetch_request_token(self.auth_url+self.request_token_path)
        url = sess.authorization_url(self.auth_url+self.authorize_path)
        return url, r['oauth_token'], r['oauth_token_secret']

    def get_query_id(self, querystring):
        return querystring['oauth_token']

    def handle_auth_callback(self, url, token, token_secret):
        sess = self.get_auth_session(dict(token=token, token_secret=token_secret))
        sess.parse_authorization_response(url)
        r = sess.fetch_access_token(self.auth_url+self.access_token_path)
        sess.token = dict(token=r['oauth_token'],
                          token_secret=r['oauth_token_secret'])
        return sess


class PlatformOAuth2(Platform):

    oauth_default_scope = None
    oauth_email_scope = None
    oauth_payment_scope = None

    def get_auth_session(self, state=None, token=None, token_updater=None):
        return OAuth2Session(self.api_key, state=state, token=token,
                             token_updater=token_updater,
                             redirect_uri=self.callback_url,
                             scope=self.oauth_default_scope)

    def get_auth_url(self, **kw):
        sess = self.get_auth_session()
        url, state = sess.authorization_url(self.auth_url)
        return url, state, ''

    def get_query_id(self, querystring):
        return querystring['state']

    def handle_auth_callback(self, url, state, unused_arg):
        sess = self.get_auth_session(state=state)
        sess.fetch_token(self.access_token_url,
                         client_secret=self.api_secret,
                         authorization_response=url)
        return sess
