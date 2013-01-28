import gittip
from aspen import Response
from aspen.utils import typecheck
from gittip.authentication import User
from gittip.participant import reserve_a_random_participant_id
from psycopg2 import IntegrityError


ACTIONS = [u'opt-in', u'connect', u'lock', u'unlock']


def _resolve(platform, username_key, username):
    """Given three unicodes, return a participant_id.
    """
    typecheck(platform, unicode, username_key, unicode, username, unicode)
    rec = gittip.db.fetchone("""

        SELECT participant_id
          FROM elsewhere
         WHERE platform=%s
           AND user_info->%s = %s

    """, (platform, username_key, username,))
    # XXX Do we want a uniqueness constraint on $username_key? Can we do that?

    if rec is None:
        raise Exception( "User %s on %s isn't known to us."
                       % (username, platform)
                        )
    return rec['participant_id']


class AccountElsewhere(object):

    platform = None  # set in subclass

    def __init__(self, user_id, user_info=None):
        """Takes a user_id and user_info, and updates the database.
        """
        typecheck(user_id, (int, unicode), user_info, (None, dict))
        self.user_id = unicode(user_id)

        if user_info is not None:
            a,b,c,d  = self.upsert(user_info)

            self.participant_id = a
            self.is_claimed = b
            self.is_locked = c
            self.balance = d


    def set_is_locked(self, is_locked):
        gittip.db.execute("""

            UPDATE elsewhere
               SET is_locked=%s
             WHERE platform=%s AND user_id=%s

        """, (is_locked, self.platform, self.user_id))


    def opt_in(self, desired_participant_id):
        """Given a desired participant_id, return a User object.
        """
        self.set_is_locked(False)
        user = User.from_id(self.participant_id)  # give them a session
        if not self.is_claimed:
            user.set_as_claimed()
            try:
                user.change_id(desired_participant_id)
                user.id = self.participant_id = desired_participant_id
            except user.ProblemChangingId:
                pass
        return user


    def upsert(self, user_info):
        """Given a dict, return a tuple.

        Platform is the name of a platform that we support (ASCII blah).
        User_id is an immutable unique identifier for the given user on the
        given platform.  Username is the user's login/username on the given
        platform. It is only used here for logging. Specifically, we don't
        reserve their username for them on Gittip if they're new here. We give
        them a random participant_id here, and they'll have a chance to change
        it if/when they opt in. User_id and username may or may not be the
        same. User_info is a dictionary of profile info per the named platform.
        All platform dicts must have an id key that corresponds to the primary
        key in the underlying table in our own db.

        The return value is a tuple: (participant_id [unicode], is_claimed
        [boolean], is_locked [boolean], balance [Decimal]).

        """
        typecheck(user_info, dict)


        # Insert the account if needed.
        # =============================
        # Do this with a transaction so that if the insert fails, the
        # participant we reserved for them is rolled back as well.

        try:
            with gittip.db.get_transaction() as txn:
                _participant_id = reserve_a_random_participant_id(txn)
                txn.execute( "INSERT INTO elsewhere "
                             "(platform, user_id, participant_id) "
                             "VALUES (%s, %s, %s)"
                           , (self.platform, self.user_id, _participant_id)
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

        for k, v in user_info.items():
            user_info[k] = unicode(v)


        participant_id = gittip.db.fetchone("""

            UPDATE elsewhere
               SET user_info=%s
             WHERE platform=%s AND user_id=%s
         RETURNING participant_id

        """, (user_info, self.platform, self.user_id))['participant_id']


        # Get a little more info to return.
        # =================================

        rec = gittip.db.fetchone("""

            SELECT claimed_time, balance, is_locked
              FROM participants
              JOIN elsewhere
                ON participants.id=participant_id
             WHERE platform=%s
               AND participants.id=%s

        """, (self.platform, participant_id))

        assert rec is not None  # sanity check


        return ( participant_id
               , rec['claimed_time'] is not None
               , rec['is_locked']
               , rec['balance']
                )
