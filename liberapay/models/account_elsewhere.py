from datetime import timedelta
import json
from urllib.parse import urlsplit, urlunsplit
import uuid
import xml.etree.ElementTree as ET

from markupsafe import Markup
from oauthlib.oauth2 import InvalidGrantError, TokenExpiredError
from pando.utils import utcnow
from postgres.orm import Model
from psycopg2 import IntegrityError
import xmltodict

from ..constants import AVATAR_QUERY, DOMAIN_RE, RATE_LIMITS, SUMMARY_MAX_SIZE
from ..cron import logger
from ..elsewhere._exceptions import BadUserId, UserNotFound
from ..exceptions import InvalidId, TooManyRequests
from ..security.crypto import constant_time_compare
from ..utils import excerpt_intro
from ..website import website


CONNECT_TOKEN_TIMEOUT = timedelta(hours=24)


class UnableToRefreshAccount(Exception): pass

class UnknownAccountElsewhere(Exception): pass


class _AccountElsewhere(Model):
    typname = "elsewhere"


class AccountElsewhere(Model):

    typname = "elsewhere_with_participant"

    def __init__(self, values):
        if self.__class__.attnames is not _AccountElsewhere.attnames:
            self.__class__.attnames = _AccountElsewhere.attnames
        elsewhere, participant = values
        self.__dict__.update(elsewhere.__dict__)
        self.set_attributes(participant=participant)
        self.platform_data = getattr(website.platforms, self.platform)

    def __repr__(self):
        return '<AccountElsewhere id=%i platform=%r user_name=%r>' % (
            self.id, self.platform, self.user_name
        )


    # Constructors
    # ============

    @classmethod
    def from_id(cls, id, _raise=True):
        """Return an existing AccountElsewhere based on id.
        """
        r = cls.db.one("""
            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE id = %s
        """, (id,))
        if r is None and _raise:
            raise InvalidId(id, cls.__name__)
        return r

    @classmethod
    def _from_thing(cls, thing, platform, value, domain):
        assert thing in ('user_id', 'user_name')
        if thing == 'user_name':
            thing = 'lower(user_name)'
            value = value.lower()
        exception = UnknownAccountElsewhere(thing, platform, value, domain)
        return cls.db.one("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform = %s
               AND domain = %s
               AND {} = %s

        """.format(thing), (platform, domain, value), default=exception)

    @classmethod
    def get_many(cls, platform, user_infos):
        accounts = []
        found = cls.db.all("""\

            SELECT (e, p)::elsewhere_with_participant
              FROM elsewhere e
              JOIN participants p ON p.id = e.participant
              JOIN jsonb_array_elements(%s::jsonb) a ON a->>0 = e.user_id AND a->>1 = e.domain
             WHERE e.platform = %s

        """, (json.dumps([[i.user_id, i.domain] for i in user_infos]), platform))
        found = {(a.user_id, a.domain): a for a in found}
        for i in user_infos:
            if (i.user_id, i.domain) in found:
                accounts.append(found[(i.user_id, i.domain)])
            else:
                accounts.append(cls.upsert(i))
        return accounts

    @classmethod
    def upsert(cls, i):
        """Insert or update a user's info.
        """

        i.info_fetched_at = utcnow()

        # Clean up avatar_url
        if i.avatar_url:
            scheme, netloc, path, query, fragment = urlsplit(i.avatar_url)
            fragment = ''
            if netloc.endswith('githubusercontent.com') or \
               netloc.endswith('gravatar.com') or \
               netloc.endswith('libravatar.org'):
                query = AVATAR_QUERY
            i.avatar_url = urlunsplit((scheme, netloc, path, query, fragment))

        # Serialize extra_info
        if isinstance(i.extra_info, ET.Element):
            i.extra_info = xmltodict.parse(ET.tostring(i.extra_info))
        i.extra_info = json.dumps(i.extra_info)

        d = dict(i.__dict__)
        d.pop('email', None)
        cols, vals = zip(*d.items())
        cols = ', '.join(cols)
        placeholders = ', '.join(['%s']*len(vals))

        def update():
            return cls.db.one("""
                UPDATE elsewhere
                   SET ({0}) = ({1})
                 WHERE platform=%s AND domain=%s AND user_id=%s
             RETURNING elsewhere.*::elsewhere_with_participant
            """.format(cols, placeholders), vals+(i.platform, i.domain, i.user_id))

        # Check for and handle a possible user_name reallocation
        if i.user_name:
            conflicts_with = cls.db.one("""
                SELECT e.*::elsewhere_with_participant
                  FROM elsewhere e
                 WHERE e.platform = %s
                   AND e.domain = %s
                   AND lower(e.user_name) = %s
                   AND e.user_id <> %s
            """, (i.platform, i.domain, i.user_name.lower(), i.user_id))
            if conflicts_with is not None:
                try:
                    conflicts_with.refresh_user_info()
                except (UnableToRefreshAccount, UserNotFound):
                    cls.db.run("""
                        UPDATE elsewhere
                           SET user_name = null
                         WHERE id = %s
                           AND platform = %s
                           AND domain = %s
                           AND user_name = %s
                    """, (conflicts_with.id, i.platform, i.domain, conflicts_with.user_name))
            del conflicts_with

        account = update() if i.user_id else None
        if not account:
            try:
                # Try to insert the account
                # We do this with a transaction so that if the insert fails, the
                # participant we reserved for them is rolled back as well.
                with cls.db.get_cursor() as cursor:
                    account = cursor.one("""
                        WITH p AS (
                                 INSERT INTO participants DEFAULT VALUES RETURNING id
                             )
                        INSERT INTO elsewhere
                                    (participant, {0})
                             VALUES ((SELECT id FROM p), {1})
                          RETURNING elsewhere.*::elsewhere_with_participant
                    """.format(cols, placeholders), vals)
            except IntegrityError:
                # The account is already in the DB, update it instead
                if i.user_name and i.user_id:
                    # Set user_id if it was missing
                    cls.db.run("""
                        UPDATE elsewhere
                           SET user_id = %s
                         WHERE platform=%s AND domain=%s AND lower(user_name)=%s
                           AND user_id IS NULL
                    """, (i.user_id, i.platform, i.domain, i.user_name.lower()))
                elif not i.user_id:
                    return cls._from_thing('user_name', i.platform, i.user_name, i.domain)
                account = update()
                if not account:
                    raise

        # Return account after propagating avatar_url to participant
        account.participant.set_attributes(avatar_url=cls.db.one("""
            UPDATE participants
               SET avatar_url = coalesce(%s, avatar_url)
             WHERE id = %s
         RETURNING avatar_url
        """, (account.avatar_url, account.participant.id)))
        return account


    # Connect tokens
    # ==============

    def check_connect_token(self, token):
        return (
            self.connect_token and
            constant_time_compare(self.connect_token, token) and
            self.connect_expires > utcnow()
        )

    def make_connect_token(self):
        token = uuid.uuid4().hex
        expires = utcnow() + CONNECT_TOKEN_TIMEOUT
        return self.save_connect_token(token, expires)

    def save_connect_token(self, token, expires):
        return self.db.one("""
            UPDATE elsewhere
               SET connect_token = %s
                 , connect_expires = %s
             WHERE id = %s
         RETURNING connect_token, connect_expires
        """, (token, expires, self.id))


    # Random Stuff
    # ============

    def get_auth_session(self):
        if not self.token:
            return
        params = dict(token=self.token)
        if 'refresh_token' in self.token:
            params['token_updater'] = self.save_token
        return self.platform_data.get_auth_session(self.domain, **params)

    @property
    def address(self):
        return self.user_name + '@' + self.domain

    @property
    def liberapay_slug(self):
        if self.user_name:
            return self.user_name + (('@' + self.domain) if self.domain else '')
        return '~' + self.user_id + ((':' + self.domain) if self.domain else '')

    @property
    def liberapay_path(self):
        return '/on/%s/%s' % (self.platform, self.liberapay_slug)

    @property
    def liberapay_url(self):
        scheme = website.canonical_scheme
        host = website.canonical_host
        platform = self.platform
        slug = self.liberapay_slug
        return "{scheme}://{host}/on/{platform}/{slug}/".format(**locals())

    @property
    def html_url(self):
        return self.platform_data.account_url.format(
            domain=self.domain,
            user_id=self.user_id,
            user_name=self.user_name,
            user_name_lower=(self.user_name or '').lower(),
            platform_data=self.platform_data
        ) if self.platform_data.account_url else '#not-available'

    @property
    def friendly_name(self):
        if self.domain:
            return self.address
        elif self.platform_data.optional_user_name:
            return self.display_name or self.user_name or self.user_id
        else:
            return self.user_name or self.display_name or self.user_id

    @property
    def friendly_name_long(self):
        r = self.friendly_name
        display_name = self.display_name
        if display_name and display_name != r:
            return '%s (%s)' % (r, display_name)
        user_name = self.user_name
        if user_name and user_name != r:
            return '%s (%s)' % (r, user_name)
        return r

    def get_excerpt(self, size=SUMMARY_MAX_SIZE):
        return excerpt_intro(Markup(self.description or '').striptags(), size)

    def save_token(self, token):
        """Saves the given access token in the database.
        """
        self.db.run("""
            UPDATE elsewhere
               SET token = %s
             WHERE id=%s
        """, (json.dumps(token), self.id))
        self.set_attributes(token=token)

    def refresh_user_info(self):
        """Refetch the account's info from the platform and update it in the DB.

        Returns a new `AccountElsewhere` instance containing the updated data.
        """
        platform = self.platform_data
        sess = self.get_auth_session()
        if sess:
            try:
                info = platform.get_user_self_info(self.domain, sess)
                return self.upsert(info)
            except (InvalidGrantError, TokenExpiredError):
                self.db.run("UPDATE elsewhere SET token = NULL WHERE id = %s", (self.id,))
                sess = None
        # We don't have a valid user token, try a non-authenticated request
        if getattr(self.platform_data, 'api_requires_user_token', False):
            raise UnableToRefreshAccount(self.id, self.platform)
        if self.user_id and hasattr(self.platform_data, 'api_user_info_path'):
            type_of_id, id_value = 'user_id', self.user_id
        elif self.user_name and hasattr(self.platform_data, 'api_user_name_info_path'):
            type_of_id, id_value = 'user_name', self.user_name
        else:
            raise UnableToRefreshAccount(self.id, self.platform)
        try:
            info = platform.get_user_info(self.domain, type_of_id, id_value, uncertain=False)
        except UserNotFound:
            if not self.missing_since:
                self.db.run("""
                    UPDATE elsewhere
                       SET missing_since = current_timestamp
                     WHERE id = %s
                       AND missing_since IS NULL
                """, (self.id,))
            raise
        return self.upsert(info)


def get_account_elsewhere(website, state, api_lookup=True):
    request = state['request']
    path = request.path
    response = state['response']
    platform = website.platforms.get(path['platform'])
    if platform is None:
        raise response.error(404)
    uid = path['user_name']
    if uid[:1] == '~':
        key = 'user_id'
        uid = uid[1:]
    else:
        key = 'user_name'
        if uid[:1] == '@':
            uid = uid[1:]
    split = uid.rsplit('@', 1)
    uid, domain = split if len(split) == 2 else (uid, '')
    if bool(domain) == platform.single_domain:
        raise response.error(404)
    try:
        domain = domain.encode('idna').decode('ascii')
    except UnicodeEncodeError as e:
        raise response.error(404, str(e))
    if domain and not DOMAIN_RE.match(domain):
        raise response.error(404, "invalid domain name")
    try:
        account = AccountElsewhere._from_thing(key, platform.name, uid, domain)
    except UnknownAccountElsewhere:
        account = None
    if not account:
        if not account and not api_lookup:
            raise response.error(404)
        website.db.hit_rate_limit('elsewhere-lookup.ip-addr', request.source, TooManyRequests)
        try:
            user_info = platform.get_user_info(domain, key, uid)
        except NotImplementedError:
            _ = state['_']
            raise response.error(404, _(
                "The {platform} user you're looking for hasn't joined Liberapay, "
                "and it's not possible to create a stub profile for them.",
                platform=platform.display_name
            ))
        except (BadUserId, UserNotFound) as e:
            _ = state['_']
            if isinstance(e, BadUserId):
                err = _("'{0}' doesn't seem to be a valid user id on {platform}.",
                        uid, platform=platform.display_name)
                raise response.error(400, err)
            err = _("There doesn't seem to be a user named {0} on {1}.",
                    uid, platform.display_name)
            raise response.error(404, err)
        account = AccountElsewhere.upsert(user_info)
    return platform, account


def refetch_elsewhere_data():
    # Note: the rate_limiting table is used to avoid blocking on errors
    rl_prefix = 'refetch_elsewhere_data'
    rl_cap, rl_period = RATE_LIMITS[rl_prefix]
    account = website.db.one("""
        SELECT (e, p)::elsewhere_with_participant
          FROM elsewhere e
          JOIN participants p ON p.id = e.participant
         WHERE e.info_fetched_at < now() - interval '90 days'
           AND (e.missing_since IS NULL OR e.missing_since > (current_timestamp - interval '30 days'))
           AND (p.status = 'active' OR p.receiving > 0)
           AND (e.token IS NOT NULL OR e.platform <> 'google')
           AND check_rate_limit(%s || e.id::text, %s, %s)
      ORDER BY e.info_fetched_at ASC
         LIMIT 1
    """, (rl_prefix + ':', rl_cap, rl_period))
    if not account:
        return
    rl_key = str(account.id)
    website.db.hit_rate_limit(rl_prefix, rl_key)
    logger.debug(
        "Refetching data of %s account %s (participant %i)" %
        (account.platform, account.user_id, account.participant.id)
    )
    try:
        account.refresh_user_info()
    except (UnableToRefreshAccount, UserNotFound) as e:
        logger.debug("The refetch failed: %s" % e)
        return
    # The update was successful, clean up the rate_limiting table
    website.db.run("DELETE FROM rate_limiting WHERE key = %s", (rl_prefix + ':' + rl_key,))
