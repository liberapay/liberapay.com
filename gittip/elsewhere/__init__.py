"""This subpackage contains functionality for working with accounts elsewhere.
"""
from __future__ import print_function, unicode_literals

from aspen.utils import typecheck
from psycopg2 import IntegrityError

import gittip
from gittip.security.user import User
from gittip.models.participant import Participant, reserve_a_random_username
from gittip.models.participant import ProblemChangingUsername


ACTIONS = [u'opt-in', u'connect', u'lock', u'unlock']


def _resolve(platform, username_key, username):
    """Given three unicodes, return a username.
    """
    typecheck(platform, unicode, username_key, unicode, username, unicode)
    participant = gittip.db.one("""

        SELECT participant
          FROM elsewhere
         WHERE platform=%s
           AND user_info->%s = %s

    """, (platform, username_key, username,))
    # XXX Do we want a uniqueness constraint on $username_key? Can we do that?

    if participant is None:
        raise Exception( "User %s on %s isn't known to us."
                       % (username, platform)
                        )
    return participant


class AccountElsewhere(object):

    platform = None  # set in subclass

    def __init__(self, user_id, user_info=None):
        """Takes a user_id and user_info, and updates the database.
        """
        typecheck(user_id, (int, unicode), user_info, (None, dict))
        self.user_id = unicode(user_id)

        if user_info is not None:
            a,b,c,d  = self.upsert(user_info)

            self.participant = a
            self.is_claimed = b
            self.is_locked = c
            self.balance = d


    def get_participant(self):
        return Participant.query.get(username=self.participant)


    def set_is_locked(self, is_locked):
        gittip.db.run("""

            UPDATE elsewhere
               SET is_locked=%s
             WHERE platform=%s AND user_id=%s

        """, (is_locked, self.platform, self.user_id))


    def opt_in(self, desired_username):
        """Given a desired username, return a User object.
        """
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
            with gittip.db.get_cursor() as cursor:
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


        username = gittip.db.one("""

            UPDATE elsewhere
               SET user_info=%s
             WHERE platform=%s AND user_id=%s
         RETURNING participant

        """, (user_info, self.platform, self.user_id))


        # Get a little more info to return.
        # =================================

        rec = gittip.db.one("""

            SELECT claimed_time, balance, is_locked
              FROM participants
              JOIN elsewhere
                ON participants.username=participant
             WHERE platform=%s
               AND participants.username=%s

        """, (self.platform, username))

        assert rec is not None  # sanity check


        return ( username
               , rec.claimed_time is not None
               , rec.is_locked
               , rec.balance
                )
