"""This subpackage contains functionality for working with accounts elsewhere.
"""
from __future__ import print_function, unicode_literals
from collections import OrderedDict

from aspen.utils import typecheck
from psycopg2 import IntegrityError

import gittip
from gittip.exceptions import ProblemChangingUsername, UnknownPlatform
from gittip.utils.username import reserve_a_random_username


ACTIONS = [u'opt-in', u'connect', u'lock', u'unlock']


# when adding a new platform, add its name to this list.
# its class will automatically be set in platform_classes at import-time.
# the ordering of this list defines the ordering of platform_classes.items().
_platforms_ordered = (
    'twitter',
    'github',
    'bitbucket',
    'bountysource',
    'venmo',
)

# init-time setup is necessary for two reasons:
#   1) to allow for deterministic iter order in templates
#   2) to allow the use of platform_classes.keys() at import-time
# note that OrderedDicts retain ordering of keys after they are replaced.
platform_classes = OrderedDict([(platform, None) for platform in _platforms_ordered])


class _RegisterPlatformMeta(type):
    """Tied to AccountElsewhere to enable registration by the platform field.
    """

    def __new__(cls, name, bases, dct):
        c = super(_RegisterPlatformMeta, cls).__new__(cls, name, bases, dct)

        # register the platform and verify it was added at init-time
        c_platform = getattr(c, 'platform')
        if name == 'AccountElsewhere':
            pass
        elif c_platform not in platform_classes:
            raise UnknownPlatform(c_platform)  # has it been added to platform_classes init?
        else:
            platform_classes[c_platform] = c

        return c

class AccountElsewhere(object):

    __metaclass__ = _RegisterPlatformMeta

    platform = None  # set in subclass

    def __init__(self, db, user_id, user_info=None, existing_record=None):
        """Either:
        - Takes a user_id and user_info, and updates the database.

        Or:
        - Takes a user_id and existing_record, and constructs a "model" object out of the record
        """
        typecheck(user_id, (int, unicode), user_info, (None, dict))
        self.user_id = unicode(user_id)
        self.db = db

        if user_info is not None:
            a,b,c,d  = self.upsert(user_info)

            self.participant = a
            self.is_claimed = b
            self.is_locked = c
            self.balance = d

            self.user_info = user_info

        # hack to make this into a weird pseudo-model that can share convenience methods
        elif existing_record is not None:
            self.participant = existing_record.participant
            self.is_claimed, self.is_locked, self.balance = self.get_misc_info(self.participant)
            self.user_info = existing_record.user_info
            self.record = existing_record


    def set_is_locked(self, is_locked):
        self.db.run("""

            UPDATE elsewhere
               SET is_locked=%s
             WHERE platform=%s AND user_id=%s

        """, (is_locked, self.platform, self.user_id))


    def opt_in(self, desired_username):
        """Given a desired username, return a User object.
        """
        from gittip.security.user import User

        self.set_is_locked(False)
        user = User.from_username(self.participant)
        user.sign_in()
        assert not user.ANON, self.participant  # sanity check
        if self.is_claimed:
            newly_claimed = False
        else:
            newly_claimed = True
            user.participant.set_as_claimed()
            try:
                user.participant.change_username(desired_username)
            except ProblemChangingUsername:
                pass
        return user, newly_claimed


    def upsert(self, user_info):
        """Given a dict, return a tuple.

        User_id is an immutable unique identifier for the given user on the
        given platform.  Username is the user's login/username on the given
        platform. It is only used here for logging. Specifically, we don't
        reserve their username for them on Gittip if they're new here. We give
        them a random username here, and they'll have a chance to change it
        if/when they opt in. User_id and username may or may not be the same.
        User_info is a dictionary of profile info per the named platform.  All
        platform dicts must have an id key that corresponds to the primary key
        in the underlying table in our own db.

        The return value is a tuple: (username [unicode], is_claimed [boolean],
        is_locked [boolean], balance [Decimal]).

        """
        typecheck(user_info, dict)


        # Insert the account if needed.
        # =============================
        # Do this with a transaction so that if the insert fails, the
        # participant we reserved for them is rolled back as well.

        try:
            with self.db.get_cursor() as cursor:
                _username = reserve_a_random_username(cursor)
                cursor.execute( "INSERT INTO elsewhere "
                                "(platform, user_id, participant) "
                                "VALUES (%s, %s, %s)"
                              , (self.platform, self.user_id, _username)
                               )
        except IntegrityError:
            pass


        # Update their user_info.
        # =======================
        # Cast everything to unicode, because (I believe) hstore can take any
        # type of value, but psycopg2 can't.
        #
        #   https://postgres.heroku.com/blog/past/2012/3/14/introducing_keyvalue_data_storage_in_heroku_postgres/
        #   http://initd.org/psycopg/docs/extras.html#hstore-data-type
        #
        # XXX This clobbers things, of course, such as booleans. See
        # /on/bitbucket/%username/index.html

        for k, v in user_info.items():
            user_info[k] = unicode(v)


        username = self.db.one("""

            UPDATE elsewhere
               SET user_info=%s
             WHERE platform=%s AND user_id=%s
         RETURNING participant

        """, (user_info, self.platform, self.user_id))

        return (username,) + self.get_misc_info(username)

    def get_misc_info(self, username):
        rec = self.db.one("""

            SELECT claimed_time, balance, is_locked
              FROM participants
              JOIN elsewhere
                ON participants.username=participant
             WHERE platform=%s
               AND participants.username=%s

        """, (self.platform, username))

        assert rec is not None  # sanity check

        return ( rec.claimed_time is not None
               , rec.is_locked
               , rec.balance
                )

    def set_oauth_tokens(self, access_token, refresh_token, expires):
        """
        Updates the elsewhere row with the given access token, refresh token, and Python datetime
        """

        self.db.run("""
            UPDATE elsewhere 
            SET (access_token, refresh_token, expires) 
            = (%s, %s, %s) 
            WHERE platform=%s AND user_id=%s
        """, (access_token, refresh_token, expires, self.platform, self.user_id))
