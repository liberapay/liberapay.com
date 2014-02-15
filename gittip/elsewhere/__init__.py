"""This subpackage contains functionality for working with accounts elsewhere.
"""
from __future__ import division, print_function, unicode_literals

from collections import OrderedDict
from datetime import datetime
import hashlib
import json
import logging
from urllib import quote
from urlparse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from aspen import log, Response
from aspen.utils import to_age, typecheck, utc
from psycopg2 import IntegrityError
from requests_oauthlib import OAuth1Session, OAuth2Session
import xmltodict

from gittip.elsewhere._extractors import not_available
from gittip.utils.username import reserve_a_random_username


ACTIONS = {'opt-in', 'connect', 'lock', 'unlock'}
PLATFORMS = 'bitbucket bountysource github openstreetmap twitter venmo'.split()


class UnknownAccountElsewhere(Exception): pass


class PlatformRegistry(object):
    """Registry of platforms we support connecting to Gittip accounts.
    """
    def __init__(self, platforms):
        self.__dict__ = OrderedDict((p.name, p) for p in platforms)

    def __contains__(self, platform):
        return platform.name in self.__dict__

    def __iter__(self):
        return iter(self.__dict__.values())


class Platform(object):

    # "x" stands for "extract"
    x_user_info = lambda self, info: info
    x_user_id = not_available
    x_user_name = not_available
    x_display_name = not_available
    x_email = not_available
    x_gravatar_id = not_available
    x_avatar_url = not_available

    required_attrs = ( 'account_url'
                     , 'display_name'
                     , 'icon'
                     , 'name'
                     )

    def __init__(self, db, api_key, api_secret, callback_url, api_url=None, auth_url=None):
        self.db = db
        self.api_key = api_key
        self.api_secret = api_secret
        self.callback_url = callback_url
        if api_url:
            self.api_url = api_url
        if auth_url:
            self.auth_url = auth_url
        elif not getattr(self, 'auth_url', None):
            self.auth_url = self.api_url
        # Make sure the subclass was implemented properly.
        missing_attrs = [a for a in self.required_attrs if not hasattr(self, a)]
        if missing_attrs:
            msg = "The class %s is missing these required attributes: %s"
            msg %= self.__class__.__name__, ', '.join(missing_attrs)
            raise AttributeError(msg)

    def get(self, path, sess=None, **kw):
        if not sess:
            sess = self.get_auth_session()
        response = sess.get(self.api_url+path, **kw)

        # Check status
        status = response.status_code
        if status == 404:
            raise Response(404)
        elif status != 200:
            log('{} api responded with {}:\n{}'.format(self.name, status, response.text)
               , level=logging.ERROR)
            raise Response(500, '{} lookup failed with {}'.format(self.name, status))

        # Check ratelimit headers
        prefix = getattr(self, 'ratelimit_headers_prefix', None)
        if prefix:
            limit = response.headers[prefix+'limit']
            remaining = response.headers[prefix+'remaining']
            reset = response.headers[prefix+'reset']
            try:
                limit, remaining, reset = int(limit), int(remaining), int(reset)
            except (TypeError, ValueError):
                d = dict(limit=limit, remaining=remaining, reset=reset)
                log('Got weird rate headers from %s: %s' % (self.name, d))
            else:
                percent_remaining = remaining/limit
                if percent_remaining < 0.5:
                    reset = to_age(datetime.fromtimestamp(reset, tz=utc))
                    log_msg = (
                        '{0} API: {1:.1%} of ratelimit has been consumed, '
                        '{2} requests remaining, resets {3}.'
                    ).format(self.name, 1 - percent_remaining, remaining, reset)
                    log_lvl = logging.WARNING
                    if percent_remaining < 0.2:
                        log_lvl = logging.ERROR
                    elif percent_remaining < 0.05:
                        log_lvl = logging.CRITICAL
                    log(log_msg, log_lvl)

        return response

    def get_account(self, user_name):
        """Given a user_name on the platform, return an AccountElsewhere object.
        """
        try:
            return self.get_account_from_db(user_name)
        except UnknownAccountElsewhere:
            return self.get_account_from_api(user_name)

    def get_account_from_api(self, user_name):
        return self.upsert(*self.get_user_info(user_name))

    def get_account_from_db(self, user_name):
        """Given a user_name on the platform, return an AccountElsewhere object.

        If the account is unknown to us, we raise UnknownAccountElsewhere.
        """
        return self.db.one("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform = %s
               AND user_name = %s

        """, (self.name, user_name), default=UnknownAccountElsewhere)

    def get_user_info(self, user_name, sess=None):
        try:
            path = self.api_user_info_path.format(user_name=quote(user_name))
        except KeyError:
            raise Response(404)
        response = self.get(path, sess=sess)
        return self.parse_user_info(response)

    def get_user_self_info(self, sess):
        response = self.get(self.api_user_self_info_path, sess=sess)
        return self.parse_user_info(response)

    def parse_user_info(self, response):
        if self.api_format == 'json':
            info = response.json()
        elif self.api_format == 'xml':
            info = ET.fromstring(response.content)
        else:
            raise ValueError('unknown API format: %(api_format)s' % self)
        return self.extract_user_info(info)

    def extract_user_info(self, info):
        info = self.x_user_info(info)
        user_name = self.x_user_name(info)
        if self.x_user_id.__func__ is not_available:
            user_id = user_name
        else:
            user_id = self.x_user_id(info)
        assert user_id is not None
        user_id = unicode(user_id)
        assert len(user_id) > 0
        display_name = self.x_display_name(info, None)
        email = self.x_email(info, None)
        gravatar_id = self.x_gravatar_id(info, None)
        if email and not gravatar_id:
            gravatar_id = hashlib.md5(email.strip().lower()).hexdigest()
        if gravatar_id:
            avatar_url = 'https://www.gravatar.com/avatar/'+gravatar_id
        else:
            avatar_url = self.x_avatar_url(info, None)
        return user_id, user_name, display_name, email, avatar_url, info

    def save_token(self, user_id, token, refresh_token=None, expires=None):
        """Saves the given access token in the database.
        """
        self.db.run("""
            UPDATE elsewhere
            SET (access_token, refresh_token, expires) = (%s, %s, %s)
            WHERE platform=%s AND user_id=%s
        """, (token, refresh_token, expires, self.name, user_id))

    def upsert(self, user_id, user_name, display_name, email, avatar_url, extra_info):
        """Insert or update the user's info.
        """
        typecheck(user_id, unicode)

        # Clean up avatar_url
        if avatar_url:
            scheme, netloc, path, query, fragment = urlsplit(avatar_url)
            fragment = ''
            if netloc.endswith('gravatar.com'):
                query = 's=128'
            avatar_url = urlunsplit((scheme, netloc, path, query, fragment))

        # Serialize extra_info
        if isinstance(extra_info, ET.Element):
            extra_info = xmltodict.parse(ET.tostring(extra_info))
        extra_info = json.dumps(extra_info)

        cols = 'user_id, user_name, display_name, email, avatar_url, extra_info'
        args = (user_id, user_name, display_name, email, avatar_url, extra_info)

        try:
            # Try to insert the account
            # We do this with a transaction so that if the insert fails, the
            # participant we reserved for them is rolled back as well.
            with self.db.get_cursor() as cursor:
                username = reserve_a_random_username(cursor)
                cursor.execute("""
                    INSERT INTO elsewhere
                                (participant, platform, {0})
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """.format(cols), (username, self.name)+args)
        except IntegrityError:
            # The account is already in the DB, update it instead
            username = self.db.one("""
                UPDATE elsewhere
                   SET ({0}) = (%s, %s, %s, %s, %s, %s)
                 WHERE platform=%s AND user_id=%s
             RETURNING participant
            """.format(cols), args+(self.name, user_id))

        # Propagate avatar_url to participant
        self.db.run("""
            UPDATE participants p
               SET avatar_url = (
                       SELECT avatar_url
                         FROM elsewhere
                        WHERE participant = p.username
                     ORDER BY platform = 'github' DESC,
                              avatar_url LIKE '%%gravatar.com%%' DESC
                        LIMIT 1
                   )
             WHERE p.username = %s
        """, (username,))

        # Now delegate to get_account_from_db
        return self.get_account_from_db(user_name)


class PlatformOAuth1(Platform):

    request_token_path = '/oauth/request_token'
    authorize_path = '/oauth/authorize'
    access_token_path = '/oauth/access_token'

    def get_auth_session(self, token=None, token_secret=None):
        return OAuth1Session(self.api_key, self.api_secret, token, token_secret,
                             callback_uri=self.callback_url)

    def get_auth_url(self, **kw):
        sess = self.get_auth_session()
        r = sess.fetch_request_token(self.auth_url+self.request_token_path)
        url = sess.authorization_url(self.auth_url+self.authorize_path)
        return url, r['oauth_token'], r['oauth_token_secret']

    def get_query_id(self, querystring):
        return querystring['oauth_token']

    def handle_auth_callback(self, url, token, token_secret):
        sess = self.get_auth_session(token=token, token_secret=token_secret)
        sess.parse_authorization_response(url)
        sess.fetch_access_token(self.auth_url+self.access_token_path)
        return sess


class PlatformOAuth2(Platform):

    oauth_default_scope = None
    oauth_email_scope = None
    oauth_payment_scope = None

    def get_auth_session(self, state=None, token=None):
        return OAuth2Session(self.api_key, state=state, token=token,
                             redirect_uri=self.callback_url,
                             scope=self.oauth_default_scope)

    def get_auth_url(self, **kw):
        sess = self.get_auth_session()
        url, state = sess.authorization_url(self.auth_url+'/authorize')
        return url, state, ''

    def get_query_id(self, querystring):
        return querystring['state']

    def handle_auth_callback(self, url, state, unused_arg):
        sess = self.get_auth_session(state=state)
        sess.fetch_token(self.auth_url+'/access_token',
                         client_secret=self.api_secret,
                         authorization_response=url)
        return sess
