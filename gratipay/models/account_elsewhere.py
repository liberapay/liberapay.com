from __future__ import absolute_import, division, print_function, unicode_literals

import json
from postgres.orm import Model
from psycopg2 import IntegrityError
from urlparse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import xmltodict

from aspen import Response
from gratipay.exceptions import ProblemChangingUsername
from gratipay.utils.username import safely_reserve_a_username


class UnknownAccountElsewhere(Exception): pass


class AccountElsewhere(Model):

    typname = "elsewhere_with_participant"

    def __init__(self, *args, **kwargs):
        super(AccountElsewhere, self).__init__(*args, **kwargs)
        self.platform_data = getattr(self.platforms, self.platform)


    # Constructors
    # ============

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
        exception = UnknownAccountElsewhere(thing, platform, value)
        return cls.db.one("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform = %s
               AND {} = %s

        """.format(thing), (platform, value), default=exception)

    @classmethod
    def get_many(cls, platform, user_infos):
        accounts = cls.db.all("""\

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform = %s
               AND user_id = any(%s)

        """, (platform, [i.user_id for i in user_infos]))
        found_user_ids = set(a.user_id for a in accounts)
        for i in user_infos:
            if i.user_id not in found_user_ids:
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
                query = 's=128'
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
                username = safely_reserve_a_username(cursor)
                cursor.execute("""
                    INSERT INTO elsewhere
                                (participant, {0})
                         VALUES (%s, {1})
                """.format(cols, placeholders), (username,)+vals)
                # Propagate elsewhere.is_team to participants.number
                if i.is_team:
                    cursor.execute("""
                        UPDATE participants
                           SET number = 'plural'::participant_number
                         WHERE username = %s
                    """, (username,))
        except IntegrityError:
            # The account is already in the DB, update it instead
            username = cls.db.one("""
                UPDATE elsewhere
                   SET ({0}) = ({1})
                 WHERE platform=%s AND user_id=%s
             RETURNING participant
            """.format(cols, placeholders), vals+(i.platform, i.user_id))
            if not username:
                raise

        # Return account after propagating avatar_url to participant
        account = AccountElsewhere.from_user_id(i.platform, i.user_id)
        account.participant.update_avatar()
        return account


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
    def html_url(self):
        return self.platform_data.account_url.format(
            user_id=self.user_id,
            user_name=self.user_name,
            platform_data=self.platform_data
        )

    def opt_in(self, desired_username):
        """Given a desired username, return a User object.
        """
        from gratipay.security.user import User
        user = User.from_username(self.participant.username)
        assert not user.ANON, self.participant  # sanity check
        if self.participant.is_claimed:
            newly_claimed = False
        else:
            newly_claimed = True
            user.participant.set_as_claimed()
            try:
                user.participant.change_username(desired_username)
            except ProblemChangingUsername:
                pass
        if user.participant.is_closed:
            user.participant.update_is_closed(False)
        return user, newly_claimed

    def save_token(self, token):
        """Saves the given access token in the database.
        """
        self.db.run("""
            UPDATE elsewhere
               SET token = %s
             WHERE id=%s
        """, (token, self.id))
        self.set_attributes(token=token)


def get_account_elsewhere(website, request):
    path = request.line.uri.path
    platform = getattr(website.platforms, path['platform'], None)
    if platform is None:
        raise Response(404)
    user_name = path['user_name']
    try:
        account = AccountElsewhere.from_user_name(platform.name, user_name)
    except UnknownAccountElsewhere:
        account = None
    if not account:
        try:
            user_info = platform.get_user_info(user_name)
        except Response:
            raise Response(404, 'The user {} does not exist on {}'.format( user_name, platform.display_name))
        account = AccountElsewhere.upsert(user_info)
    return platform, account
