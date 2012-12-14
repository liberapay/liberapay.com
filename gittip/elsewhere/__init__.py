from aspen import log
from aspen.utils import typecheck
from gittip import db
from gittip.participant import reserve_a_random_participant_id
from psycopg2 import IntegrityError


class AccountElsewhere(object):
    pass


def upsert(platform, user_id, username, user_info):
    """Given str, unicode, unicode, and dict, return unicode and boolean.

    Platform is the name of a platform that we support (ASCII blah). User_id is
    an immutable unique identifier for the given user on the given platform.
    Username is the user's login/username on the given platform. It is only
    used here for logging. Specifically, we don't reserve their username for
    them on Gittip if they're new here. We give them a random participant_id
    here, and they'll have a chance to change it if/when they opt in. User_id
    and username may or may not be the same. User_info is a dictionary of
    profile info per the named platform. All platform dicts must have an id key
    that corresponds to the primary key in the underlying table in our own db.

    The return value is a tuple: (participant_id [unicode], is_claimed
    [boolean], is_locked [boolean], balance [Decimal]).

    """
    typecheck( platform, str
             , user_id, (int, unicode)
             , username, unicode
             , user_info, dict
              )
    user_id = unicode(user_id)


    # Create a new participant.
    # =========================

    participant_id = reserve_a_random_participant_id()


    # Upsert the account elsewhere.
    # =============================

    INSERT = """\

        INSERT INTO elsewhere
                    (platform, user_id, participant_id)
             VALUES (%s, %s, %s)

    """
    try:
        db.execute(INSERT, (platform, user_id, participant_id))
    except IntegrityError:

        # That account elsewhere is already in our db. Back out the stub
        # participant we just created.

        db.execute("DELETE FROM participants WHERE id=%s", (participant_id,))

    UPDATE = """\

        UPDATE elsewhere
           SET user_info=%s
         WHERE platform=%s AND user_id=%s
     RETURNING participant_id

    """
    for k, v in user_info.items():
        # Cast everything to unicode. I believe hstore can take any type of
        # value, but psycopg2 can't.
        # https://postgres.heroku.com/blog/past/2012/3/14/introducing_keyvalue_data_storage_in_heroku_postgres/
        # http://initd.org/psycopg/docs/extras.html#hstore-data-type
        user_info[k] = unicode(v)
    rec = db.fetchone(UPDATE, (user_info, platform, user_id))
    participant_id = rec['participant_id']


    # Get a little more info to return.
    # =================================

    rec = db.fetchone( "SELECT claimed_time, balance, is_locked "
                       "FROM participants "
                       "JOIN elsewhere ON participants.id = participant_id "
                       "WHERE participants.id=%s"
                     , (participant_id,)
                      )
    assert rec is not None  # sanity check


    return ( participant_id
           , rec['claimed_time'] is not None
           , rec['is_locked']
           , rec['balance']
            )
