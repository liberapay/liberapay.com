from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import timedelta
import json
import uuid
import xml.etree.ElementTree as ET

from six.moves.urllib.parse import urlsplit, urlunsplit

from aspen import Response
from aspen.utils import utcnow
from postgres.orm import Model
from psycopg2 import IntegrityError
import xmltodict

import liberapay
from liberapay.security.crypto import constant_time_compare


CONNECT_TOKEN_TIMEOUT = timedelta(hours=24)


class UnknownAccountElsewhere(Exception): pass


class AccountElsewhere(Model):

    typname = "elsewhere_with_participant"

    def __init__(self, *args, **kwargs):
        super(AccountElsewhere, self).__init__(*args, **kwargs)
        self.platform_data = getattr(self.platforms, self.platform)


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
    def from_user_id(cls, platform, user_id):
        """Return an existing AccountElsewhere based on platform and user_id.
        """
        return cls._from_thing('user_id', platform, user_id)

    @classmethod
    def from_user_name(cls, platform, user_name):
        """Return an existing AccountElsewhere based on platform and user_name.
        """
        return cls._from_thing('user_name', platform, user_name)

    @classmethod
    def _from_thing(cls, thing, platform, value):
        assert thing in ('user_id', 'user_name')
        if thing == 'user_name':
            thing = 'lower(user_name)'
            value = value.lower()
        exception = UnknownAccountElsewhere(thing, platform, value)
        return cls.db.one("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform = %s
               AND {} = %s

        """.format(thing), (platform, value), default=exception)

    @classmethod
    def get_many(cls, platform, user_infos):
        accounts = []
        found = cls.db.all("""\

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform = %s
               AND user_id = any(%s)

        """, (platform, [i.user_id for i in user_infos]))
        found = {a.user_id: a for a in found}
        for i in user_infos:
            if i.user_id in found:
                accounts.append(found[i.user_id])
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
               netloc.endswith('gravatar.com'):
                query = 's=160'
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
            account = cls.db.one("""
                UPDATE elsewhere
                   SET ({0}) = ({1})
                 WHERE platform=%s AND user_id=%s
             RETURNING elsewhere.*::elsewhere_with_participant
            """.format(cols, placeholders), vals+(i.platform, i.user_id))
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
        return self.platform_data.get_auth_session(**params)

    @property
    def liberapay_slug(self):
        return self.user_name or ('~' + self.user_id)

    @property
    def liberapay_url(self):
        scheme = liberapay.canonical_scheme
        host = liberapay.canonical_host
        platform = self.platform
        slug = self.liberapay_slug
        return "{scheme}://{host}/on/{platform}/{slug}/".format(**locals())

    @property
    def html_url(self):
        return self.platform_data.account_url.format(
            user_id=self.user_id,
            user_name=self.user_name,
            platform_data=self.platform_data
        )

    @property
    def friendly_name(self):
        if getattr(self.platform, 'optional_user_name', False):
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

    def save_token(self, token):
        """Saves the given access token in the database.
        """
        self.db.run("""
            UPDATE elsewhere
               SET token = %s
             WHERE id=%s
        """, (token, self.id))
        self.set_attributes(token=token)


def get_account_elsewhere(website, state, api_lookup=True):
    path = state['request'].line.uri.path
    platform = getattr(website.platforms, path['platform'], None)
    if platform is None:
        raise Response(404)
    uid = path['user_name']
    if uid[:1] == '~':
        key = 'user_id'
        uid = uid[1:]
    else:
        key = 'user_name'
    try:
        account = AccountElsewhere._from_thing(key, platform.name, uid)
    except UnknownAccountElsewhere:
        account = None
    if not account:
        if not api_lookup:
            raise Response(404)
        try:
            user_info = platform.get_user_info(key, uid)
        except Response as r:
            if r.code == 404:
                _ = state['_']
                err = _("There doesn't seem to be a user named {0} on {1}.",
                        uid, platform.display_name)
                raise Response(404, err)
            raise
        account = AccountElsewhere.upsert(user_info)
    return platform, account
