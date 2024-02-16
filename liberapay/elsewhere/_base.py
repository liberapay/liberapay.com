from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Literal
from urllib.parse import quote as urlquote, urlsplit
import warnings
import xml.etree.ElementTree as ET

from babel.dates import format_timedelta
from cached_property import cached_property
from dateutil.parser import parse as parse_date
from pando.utils import utc
from oauthlib.oauth2 import BackendApplicationClient, InvalidGrantError, TokenExpiredError
from requests import Session
from requests_oauthlib import OAuth1Session, OAuth2Session

from liberapay.exceptions import TooManyRequests
from liberapay.website import website

from ._extractors import not_available


logger = logging.getLogger('liberapay.elsewhere')


class APIEndpoint(str):

    use_session = True

    def __new__(cls, path, **attrs):
        self = str.__new__(cls, path)
        self.__dict__.update(attrs)
        return self

    def __init__(self, path, **attrs):
        pass


class UserInfo:
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


class RepoInfo:
    pass


def parse_as_json(response):
    try:
        return response.json()
    except Exception as e:
        raise InvalidServerResponse(f"{e.__class__.__name__}: {e}")


def parse_as_xml(response):
    try:
        return ET.fromstring(response.content)
    except Exception as e:
        raise InvalidServerResponse(f"{e.__class__.__name__}: {e}")


class Platform:

    has_teams = False
    optional_user_name = False
    single_domain = True

    # "x" stands for "extract"
    x_domain = not_available
    x_user_info = not_available
    x_user_id = not_available
    x_user_name = not_available
    x_display_name = not_available
    x_email = not_available
    x_gravatar_id = not_available
    x_avatar_url = not_available
    x_is_team = not_available
    x_description = not_available

    x_repo_owner_id = not_available

    required_attrs = ('account_url', 'display_name', 'name')

    def __init__(self, api_key, api_secret, callback_url, api_url=None, auth_url=None,
                 api_timeout=20.0, app_name=None, app_url=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.callback_url = callback_url
        if api_url:
            self.api_url = api_url
        if auth_url:
            self.auth_url = auth_url
        elif not getattr(self, 'auth_url', None):
            self.auth_url = self.api_url
        self.api_timeout = api_timeout
        self.app_name = app_name
        self.app_url = app_url
        self.credentials_cache = {}
        domain = urlsplit(self.api_url).hostname
        self.domain = domain if '{' not in domain else None

        # Determine the appropriate response parser using `self.api_format`
        api_format = getattr(self, 'api_format', None)
        if api_format == 'json':
            self.api_parser = parse_as_json
        elif api_format == 'xml':
            self.api_parser = parse_as_xml
        elif api_format:
            raise ValueError('unknown API format: '+str(api_format))

        # Make sure the subclass was implemented properly.
        missing_attrs = [a for a in self.required_attrs if not hasattr(self, a)]
        if missing_attrs:
            msg = "The class %s is missing these required attributes: %s"
            msg %= self.__class__.__name__, ', '.join(missing_attrs)
            raise AttributeError(msg)

    def api_request(self, method, domain, path, sess=None, error_handler=True, **kw):
        url = self.api_url.format(domain=domain) + path
        domain = domain or self.domain
        is_user_session = bool(sess)
        if not sess:
            sess = self.get_app_session(domain)
            state = website.state.get(None)
            if state:
                source = state['request'].source
                website.db.hit_rate_limit('elsewhere-lookup.ip-addr', source, TooManyRequests)
        kw.setdefault('timeout', self.api_timeout)
        if hasattr(self, 'api_headers'):
            kw.setdefault('headers', {}).update(self.api_headers)
        response = sess.request(method, url, **kw)

        if not is_user_session:
            limit, remaining, reset = self.get_ratelimit_headers(response)
            self.log_ratelimit_headers(domain, limit, remaining, reset)

        # Check response status
        if error_handler is True:
            error_handler = self.api_error_handler
        status = response.status_code
        if status not in (200, 201) and error_handler:
            error_handler(response, is_user_session, domain)

        return response

    def api_get(self, domain, path, sess=None, **kw):
        """
        Given a `path` (e.g. /users/foo), this function sends a GET request to
        the platform's API (e.g. https://api.github.com/users/foo).

        The response is returned, after checking its status code and ratelimit
        headers.
        """
        return self.api_request('GET', domain, path, sess=sess, **kw)

    def api_error_handler(self, response, is_user_session, domain):
        response_text = response.text  # for Sentry
        status = response.status_code
        if is_user_session:
            if status == 401:
                # https://tools.ietf.org/html/rfc5849#section-3.2
                raise TokenExpiredError
            if status == 403:
                # Assume that a 403 means we need more permissions (OAuth2 scopes)
                raise InvalidGrantError
            if status == 429:
                limit, remaining, reset = self.get_ratelimit_headers(response)
                raise RateLimitError(limit, remaining, reset)
        if status != 200:
            logger.warning('{} responded with {}:\n{}'.format(
                domain or self.display_name, status, response_text
            ))
            raise HTTPError(status, response_text, self, domain)

    def get_ratelimit_headers(self, response):
        limit, remaining, reset = None, None, None
        prefix = getattr(self, 'ratelimit_headers_prefix', None)
        if prefix:
            limit = response.headers.get(prefix+'limit')
            remaining = response.headers.get(prefix+'remaining')
            reset = response.headers.get(prefix+'reset')

            try:
                limit, remaining = int(limit), int(remaining)
                if reset.isdigit():
                    reset = datetime.fromtimestamp(int(reset), tz=utc)
                else:
                    reset = parse_date(reset)
            except (OverflowError, TypeError, ValueError):
                d = dict(limit=limit, remaining=remaining, reset=reset)
                url = response.request.url.split('?', 1)[0]
                logger.warning('Got weird rate headers from <%s>: %s' % (url, d))
                limit, remaining, reset = None, None, None

        return limit, remaining, reset

    def log_ratelimit_headers(self, domain, limit, remaining, reset):
        """Emit log messages if we're running out of ratelimit.
        """
        if None in (limit, remaining, reset):
            return
        percent_remaining = remaining/limit
        if percent_remaining < 0.5:
            reset_delta = reset - datetime.now(timezone.utc)
            reset_delta = format_timedelta(reset_delta, add_direction=True, locale='en')
            log_lvl = logging.WARNING
            if percent_remaining < 0.2:
                log_lvl = logging.ERROR
            elif percent_remaining < 0.05:
                log_lvl = logging.CRITICAL
            logger.log(
                log_lvl,
                '%s: %.1f%% of ratelimit has been consumed, %i requests remaining, resets %s.',
                domain, (1 - percent_remaining) * 100, remaining, reset_delta
            )

    def extract_user_info(self, info, source):
        """
        Given a user_info object of variable type (depending on the platform),
        extract the relevant information by calling the platform's extractors
        (`x_user_name`, `x_user_id`, etc).

        `source` must be the domain from which the data was obtained.

        Returns a `UserInfo`. The `user_id` attribute is guaranteed to have a
        unique non-empty value, except when `source` doesn't match the account's
        domain, in which case `user_id` is `None`.
        """
        r = UserInfo(platform=self.name, missing_since=None)
        info = self.x_user_info(r, info, info)
        if info is None:
            return
        if type(info) is list:
            if len(info) != 1:
                if not info:
                    return
                raise ValueError("got a list with more than one element: %r" % info)
            info = info[0]
        r.domain = self.x_domain(r, info, '')
        assert r.domain is not None
        if not self.single_domain:
            assert r.domain
        r.user_name = self.x_user_name(r, info, None)
        if not self.x_user_id:
            r.user_id = r.user_name
        elif source == r.domain:
            r.user_id = self.x_user_id(r, info)
        else:
            r.user_id = None
        if r.user_id is not None:
            r.user_id = str(r.user_id)
            assert len(r.user_id) > 0
        r.display_name = self.x_display_name(r, info, None)
        r.email = self.x_email(r, info, None)
        r.avatar_url = self.x_avatar_url(r, info, None)
        if not r.avatar_url:
            gravatar_id = self.x_gravatar_id(r, info, None)
            if r.email and not gravatar_id:
                bs = r.email.strip().lower().encode('utf8')
                gravatar_id = hashlib.md5(bs).hexdigest()
            if gravatar_id:
                r.avatar_url = 'https://seccdn.libravatar.org/avatar/'+gravatar_id
        r.is_team = self.x_is_team(r, info, False)
        r.description = self.x_description(r, info, None)
        return r

    def get_team_members(self, account, page_url=None):
        """Given an AccountElsewhere, return its membership list from the API.
        """
        if not page_url:
            page_url = self.api_team_members_path.format(
                user_id=urlquote(account.user_id),
                user_name=urlquote(account.user_name or ''),
            )
        domain = account.domain
        r = self.api_get(domain, page_url)
        members, count, pages_urls = self.api_paginator(r, self.api_parser(r))
        members = [self.extract_user_info(m, domain) for m in members]
        return members, count, pages_urls

    def get_user_info(self, domain, key, value, sess=None, uncertain=True):
        """Given a user_name or user_id, get the user's info from the API.
        """
        if key == 'user_id':
            path = 'api_user_info_path'
        else:
            assert key == 'user_name'
            path = 'api_user_name_info_path'
        path = getattr(self, path, None)
        if not path:
            raise NotImplementedError(
                "%s lookup is not available for %s" % (key, self.display_name)
            )
        path = path.format(**{key: urlquote(value), 'domain': domain})
        def error_handler(response, is_user_session, domain):
            if response.status_code == 404:
                raise UserNotFound(value, key, domain, self, response.text)
            if response.status_code == 401 and is_user_session:
                raise TokenExpiredError
            if response.status_code in (400, 401, 403, 414) and uncertain:
                raise BadUserId(value, key, domain, self, response.text)
            self.api_error_handler(response, is_user_session, domain)
        response = self.api_get(domain, path, sess=sess, error_handler=error_handler)
        info = self.api_parser(response)
        if not info:
            raise UserNotFound(value, key, domain, self, response.text)
        if isinstance(info, list):
            assert len(info) == 1, info
            info = info[0]
        r = self.extract_user_info(info, domain)
        if r is None:
            raise UserNotFound(value, key, domain, self, response.text)
        return r

    def get_user_self_info(self, domain, sess):
        """Get the authenticated user's info from the API.
        """
        r = self.api_get(domain, self.api_user_self_info_path, sess=sess)
        info = self.extract_user_info(self.api_parser(r), domain)
        token = getattr(sess, 'token', None)
        if token:
            info.token = json.dumps(token)
        return info

    def get_follows_for(self, account, page_url=None, sess=None):
        if not page_url:
            page_url = self.api_follows_path.format(
                user_id=urlquote(account.user_id),
                user_name=urlquote(account.user_name or ''),
            )
        r = self.api_get(account.domain, page_url, sess=sess)
        follows, count, pages_urls = self.api_paginator(r, self.api_parser(r))
        follows = [self.extract_user_info(f, account.domain) for f in follows]
        return follows, count, pages_urls

    def extract_repo_info(self, info):
        r = RepoInfo()
        r.platform = self.name
        r.name = self.x_repo_name(r, info)
        r.slug = self.x_repo_slug(r, info)
        r.remote_id = str(self.x_repo_id(r, info))
        r.owner_id = self.x_repo_owner_id(r, info, None)
        if r.owner_id is not None:
            r.owner_id = str(r.owner_id)
        r.description = self.x_repo_description(r, info, None)
        r.last_update = self.x_repo_last_update(r, info, None)
        if r.last_update:
            r.last_update = parse_date(r.last_update)
        r.is_fork = self.x_repo_is_fork(r, info, None)
        r.stars_count = self.x_repo_stars_count(r, info, None)
        return r

    def get_repos(self, account, page_url=None, sess=None, refresh=True):
        if not page_url:
            page_url = self.api_repos_path.format(
                user_id=urlquote(account.user_id),
                user_name=urlquote(account.user_name or ''),
            )
        if not getattr(self.api_repos_path, 'use_session', True):
            sess = None
        r = self.api_get(account.domain, page_url, sess=sess)
        repos, count, pages_urls = self.api_paginator(r, self.api_parser(r))
        repos = [self.extract_repo_info(repo) for repo in repos]
        if '{user_id}' in self.api_repos_path:
            for repo in repos:
                if repo.owner_id is None:
                    repo.owner_id = account.user_id
        elif '{user_name}' in self.api_repos_path and repos and repos[0].owner_id != account.user_id:
            # https://hackerone.com/reports/452920
            if not refresh:
                raise TokenExpiredError()
            from liberapay.models.account_elsewhere import UnableToRefreshAccount
            try:
                account = account.refresh_user_info()
            except (ElsewhereError, UnableToRefreshAccount):
                raise TokenExpiredError()
            # Note: we can't pass the page_url below, because it contains the old user_name
            return self.get_repos(account, page_url=None, sess=sess, refresh=False)
        return repos, count, pages_urls

    def get_starred_repos(self, account, sess, page_url=None):
        if not page_url:
            page_url = self.api_starred_path.format(
                user_id=urlquote(account.user_id),
                user_name=urlquote(account.user_name or ''),
            )
        assert page_url[:1] == '/'
        if not getattr(self.api_starred_path, 'use_session', True):
            sess = None
        r = self.api_get(account.domain, page_url, sess=sess)
        repos, count, pages_urls = self.api_paginator(r, self.api_parser(r))
        repos = [self.extract_repo_info(repo) for repo in repos]
        return repos, count, pages_urls

    def get_credentials(self, domain):
        # 0. Single-domain platforms have a single pair of credentials
        if self.single_domain:
            return self.api_key, self.api_secret
        # 1. Look in the local cache
        r = self.credentials_cache.get(domain)
        if r:
            return r
        # 2. Look in the DB
        r = self.get_credentials_from_db(domain)
        if r:
            self.credentials_cache[domain] = r
            return r
        # 3. Create the credentials
        with website.db.get_cursor() as cursor:
            # Prevent race condition
            cursor.run("LOCK TABLE oauth_apps IN EXCLUSIVE MODE")
            r = self.get_credentials_from_db(domain)
            if r:
                return r
            # Call the API and store the new credentials
            key, secret = self.register_app(domain)
            r = cursor.one("""
                INSERT INTO oauth_apps
                            (platform, domain, key, secret)
                     VALUES (%s, %s, %s, %s)
                  RETURNING key, secret
            """, (self.name, domain, key, secret))
            self.credentials_cache[domain] = r
            return r

    def get_credentials_from_db(self, domain):
        return website.db.one("""
            SELECT key, secret
              FROM oauth_apps
             WHERE platform = %s
               AND domain = %s
        """, (self.name, domain))

    def get_CantReadMembership_url(self, account):
        return ''

    @cached_property
    def supports_follows(self):
        return bool(getattr(self, 'api_follows_path', None))


class PlatformOAuth1(Platform):

    request_token_path = '/oauth/request_token'
    authorize_path = '/oauth/authorize'
    access_token_path = '/oauth/access_token'

    def get_app_session(self, domain):
        return self.get_auth_session(domain)

    def get_auth_session(self, domain, token=None):
        args = ()
        if token:
            args = (token['token'], token['token_secret'])
        callback_url = self.callback_url.format(domain=domain)
        client_id, client_secret = self.get_credentials(domain)
        return OAuth1Session(client_id, client_secret, *args,
                             callback_uri=callback_url)

    def get_auth_url(self, domain, **kw):
        if kw:
            warnings.warn(f"{self.get_auth_url} received unknown keyword arguments: {kw}")
        sess = self.get_auth_session(domain)
        auth_url = self.auth_url.format(domain=domain)
        r = sess.fetch_request_token(auth_url+self.request_token_path)
        url = sess.authorization_url(auth_url+self.authorize_path)
        return url, r['oauth_token'], r['oauth_token_secret']

    def get_query_id(self, querystring):
        return querystring['oauth_token']

    def handle_auth_callback(self, domain, url, token, token_secret):
        sess = self.get_auth_session(domain, dict(token=token, token_secret=token_secret))
        sess.parse_authorization_response(url)
        auth_url = self.auth_url.format(domain=domain)
        r = sess.fetch_access_token(auth_url+self.access_token_path)
        sess.token = dict(token=r['oauth_token'],
                          token_secret=r['oauth_token_secret'])
        return sess


class PlatformOAuth2(Platform):

    oauth_default_scope = []
    oauth_email_scope = None
    oauth_follows_scope = ''

    can_auth_with_client_credentials = None
    use_basic_auth_for_app_session = False

    session_class = OAuth2Session

    def __init__(self, *args, **kw):
        Platform.__init__(self, *args, **kw)
        if self.can_auth_with_client_credentials:
            self.app_sessions = {}

    def get_app_session(self, domain):
        if self.can_auth_with_client_credentials:
            sess = self.app_sessions.get(domain)
            if not sess:
                client_id = self.get_credentials(domain)[0]
                if self.use_basic_auth_for_app_session:
                    sess = Session()
                    sess.auth = self.get_credentials(domain)
                else:
                    sess = self.session_class(client=BackendApplicationClient(client_id))
                self.app_sessions[domain] = sess
            if not sess.auth and not sess.token:
                access_token_url = self.access_token_url.format(domain=domain)
                client_id, client_secret = self.get_credentials(domain)
                sess.fetch_token(access_token_url, client_id=client_id,
                                 client_secret=client_secret)
            return sess
        else:
            return self.get_auth_session(domain)

    def get_auth_session(self, domain, state=None, token=None, token_updater=None,
                         extra_scopes=[]):
        callback_url = self.callback_url.format(domain=domain)
        client_id, client_secret = self.get_credentials(domain)
        credentials = dict(client_id=client_id, client_secret=client_secret)
        if token and token.get('refresh_token'):
            refresh_url = getattr(self, 'refresh_token_url', self.access_token_url)
            if refresh_url and domain:
                refresh_url = refresh_url.format(domain=domain)
        else:
            refresh_url = None
        return self.session_class(
            client_id, state=state, token=token, token_updater=token_updater,
            auto_refresh_url=refresh_url, auto_refresh_kwargs=credentials,
            redirect_uri=callback_url, scope=self.oauth_default_scope + extra_scopes
        )

    def get_auth_url(self, domain, extra_scopes=[], **kw):
        if kw:
            warnings.warn(f"{self.get_auth_url} received unknown keyword arguments: {kw}")
        sess = self.get_auth_session(domain, extra_scopes=extra_scopes)
        url, state = sess.authorization_url(self.auth_url.format(domain=domain))
        return url, state, ''

    def get_query_id(self, querystring):
        return querystring['state']

    def handle_auth_callback(self, domain, url, state, unused_arg):
        sess = self.get_auth_session(domain, state=state)
        client_secret = self.get_credentials(domain)[1]
        sess.fetch_token(self.access_token_url.format(domain=domain),
                         client_secret=client_secret,
                         authorization_response=url)
        return sess


class ElsewhereError(Exception):
    """Base class for elsewhere exceptions."""


@dataclass
class BadUserId(ElsewhereError):
    uid: str
    uid_type: Literal['user_id', 'user_name']
    domain: str
    platform: Platform
    response_text: str


class CantReadMembership(ElsewhereError):
    pass


@dataclass
class HTTPError(ElsewhereError):
    status_code: int
    text: str
    platform: Platform
    domain: str


class InvalidServerResponse(ElsewhereError):
    pass


@dataclass
class RateLimitError(ElsewhereError):
    limit: int
    remaining: int
    reset: datetime


@dataclass
class UserNotFound(ElsewhereError):
    uid: str
    uid_type: Literal['user_id', 'user_name']
    domain: str
    platform: Platform
    response_text: str
