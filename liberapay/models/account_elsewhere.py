from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta
import json
import uuid
import xml.etree.ElementTree as ET

from six.moves.urllib.parse import urlsplit, urlunsplit

from pando.utils import utcnow
from postgres.orm import Model
from psycopg2 import IntegrityError
import xmltodict

from liberapay.constants import AVATAR_QUERY, SUMMARY_MAX_SIZE
from liberapay.elsewhere._exceptions import BadUserId, UserNotFound
from liberapay.security.crypto import constant_time_compare
from liberapay.utils import excerpt_intro
from liberapay.website import website


CONNECT_TOKEN_TIMEOUT = timedelta(hours=24)


class UnknownAccountElsewhere(Exception): pass


class _AccountElsewhere(Model):
    typname = "elsewhere"


class AccountElsewhere(Model):

    typname = "elsewhere_with_participant"

    def __init__(self, raw_record):
        record = raw_record['e'].__dict__
        record['participant'] = raw_record['p']
        super(AccountElsewhere, self).__init__(record)
        self.platform_data = getattr(website.platforms, self.platform)


    # Constructors
    # ============

    @classmethod
    def from_id(cls, id):
        """Return an existing AccountElsewhere based on id.
        """
        return cls.db.one("""
            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE id = %s
        """, (id,))

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

        cols, vals = zip(*i.__dict__.items())
        cols = ', '.join(cols)
        placeholders = ', '.join(['%s']*len(vals))

        try:
            # Try to insert the account
            # We do this with a transaction so that if the insert fails, the
            # participant we reserved for them is rolled back as well.
            with cls.db.get_cursor() as cursor:
                id = cursor.one("""
                    INSERT INTO participants DEFAULT VALUES RETURNING id
                """)
                account = cursor.one("""
                    INSERT INTO elsewhere
                                (participant, {0})
                         VALUES (%s, {1})
                      RETURNING elsewhere.*::elsewhere_with_participant
                """.format(cols, placeholders), (id,)+vals)
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
            account = cls.db.one("""
                UPDATE elsewhere
                   SET ({0}) = ({1})
                 WHERE platform=%s AND domain=%s AND user_id=%s
             RETURNING elsewhere.*::elsewhere_with_participant
            """.format(cols, placeholders), vals+(i.platform, i.domain, i.user_id))
            if not account:
                raise

        # Return account after propagating avatar_url to participant
        account.participant.update_avatar()
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
        )

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

    @property
    def description(self):
        if self.extra_info:
            r = self.platform_data.x_description(None, self.extra_info, '')
        else:
            r = ''
        self.__dict__['description'] = r
        return r

    def get_excerpt(self, size=SUMMARY_MAX_SIZE):
        return excerpt_intro(self.description, size)

    def save_token(self, token):
        """Saves the given access token in the database.
        """
        self.db.run("""
            UPDATE elsewhere
               SET token = %s
             WHERE id=%s
        """, (json.dumps(token), self.id))
        self.set_attributes(token=token)


def get_account_elsewhere(website, state, api_lookup=True):
    path = state['request'].line.uri.path
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
    if domain and platform.single_domain:
        raise response.error(404)
    try:
        account = AccountElsewhere._from_thing(key, platform.name, uid, domain)
    except UnknownAccountElsewhere:
        account = None
    if not account:
        if not account and not api_lookup:
            raise response.error(404)
        try:
            user_info = platform.get_user_info(domain, key, uid)
        except NotImplementedError as e:
            raise response.error(400, e.args[0])
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
