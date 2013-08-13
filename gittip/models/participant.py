"""*Participant* is the name Gittip gives to people and groups that are known
to Gittip. We've got a ``participants`` table in the database, and a
:py:class:`Participant` class that we define here. We distinguish several kinds
of participant, based on certain properties.

 - *Stub* participants
 - *Organizations* are plural participants
 - *Teams* are plural participants with members

"""
from __future__ import unicode_literals

import datetime
import os
import random
import uuid
from decimal import Decimal

import gittip
import pytz
from psycopg2 import IntegrityError
from aspen.utils import typecheck
from gittip.models.team import Team


ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                ".,-_:@ ")
NANSWERS_THRESHOLD = 0  # configured in wireup.py


class Participant(object):
    """Represent a Gittip participant.
    """

    ################################################################
    ############### BEGIN COPY/PASTE OF ORM VERSION
    ################################################################

    @property
    def valid_tips_receiving(self):
        '''

      SELECT count(anon_1.amount) AS count_1
        FROM ( SELECT DISTINCT ON (tips.tipper)
                      tips.id AS id
                    , tips.ctime AS ctime
                    , tips.mtime AS mtime
                    , tips.tipper AS tipper
                    , tips.tippee AS tippee
                    , tips.amount AS amount
                 FROM tips
                 JOIN participants ON tips.tipper = participants.username
                WHERE %(param_1)s = tips.tippee
                  AND participants.is_suspicious IS NOT true
                  AND participants.last_bill_result = %(last_bill_result_1)s
             ORDER BY tips.tipper, tips.mtime DESC
              ) AS anon_1
       WHERE anon_1.amount > %(amount_1)s

        '''
        return self.tips_receiving \
                   .join( Participant
                        , Tip.tipper.op('=')(Participant.username)
                         ) \
                   .filter( 'participants.is_suspicious IS NOT true'
                          , Participant.last_bill_result == ''
                           )

    def get_number_of_backers(self):
        amount_column = self.valid_tips_receiving.subquery().columns.amount
        count = func.count(amount_column)
        nbackers = db.session.query(count).filter(amount_column > 0).one()[0]
        return nbackers

    def get_og_title(self):
        out = self.username
        receiving = self.get_dollars_receiving()
        giving = self.get_dollars_giving()
        if (giving > receiving) and not self.anonymous:
            out += " gives $%.2f/wk" % giving
        elif receiving > 0:
            out += " receives $%.2f/wk" % receiving
        else:
            out += " is"
        return out + " on Gittip"

    def get_age_in_seconds(self):
        out = -1
        if self.claimed_time is not None:
            now = datetime.datetime.now(self.claimed_time.tzinfo)
            out = (now - self.claimed_time).total_seconds()
        return out

    ################################################################
    ############### END COPY/PASTE OF ORM VERSION
    ################################################################


    def __init__(self, username):
        typecheck(username, (unicode, None))
        self.username = username

    def __eq__(self, other):
        return self.username == other.username

    def __ne__(self, other):
        return self.username != other.username


    def get_details(self):
        """Return a dictionary.
        """
        SELECT = """

            SELECT *
              FROM participants
             WHERE username = %s

        """
        return gittip.db.one_or_zero(SELECT, (self.username,))


    @classmethod
    def from_session_token(cls, token):
        SESSION = ("SELECT * FROM participants "
                   "WHERE is_suspicious IS NOT true "
                   "AND session_token=%s")
        session = cls.load_session(SESSION, token)
        return cls(session)

    @classmethod
    def from_id(cls, participant_id):
        from gittip import db
        SESSION = ("SELECT * FROM participants "
                   "WHERE is_suspicious IS NOT true "
                   "AND id=%s")
        session = cls.load_session(SESSION, participant_id)
        session['session_token'] = uuid.uuid4().hex
        db.execute( "UPDATE participants SET session_token=%s WHERE id=%s"
                  , (session['session_token'], participant_id)
                   )
        return cls(session)

    @staticmethod
    def load_session(SESSION, val):
        from gittip import db
        # XXX All messed up. Fix me!
        return db.one_or_zero(SESSION, (val,), zero={})
        return out


    def is_singular(self):
        rec = gittip.db.one_or_zero("SELECT number FROM participants "
                                    "WHERE username = %s", (self.username,))

        return rec['number'] == 'singular'

    def is_plural(self):
        rec = gittip.db.one_or_zero("SELECT number FROM participants "
                                    "WHERE username = %s", (self.username,))

        return rec['number'] == 'plural'


    def get_teams(self):
        """Return a list of teams this user is a member of.
        """
        return gittip.db.all("""

            SELECT team AS name
                 , ( SELECT count(*)
                       FROM current_memberships
                      WHERE team=x.team
                    ) AS nmembers
              FROM current_memberships x
             WHERE member=%s;

        """, (self.username,))


    # API Key
    # =======

    def recreate_api_key(self):
        api_key = str(uuid.uuid4())
        SQL = "UPDATE participants SET api_key=%s WHERE username=%s"
        gittip.db.run(SQL, (api_key, self.username))
        return api_key


    # Claiming
    # ========
    # An unclaimed Participant is a stub that's created when someone pledges to
    # give to an AccountElsewhere that's not been connected on Gittip yet.

    # XXX

    def resolve_unclaimed(self):
        if self.accounts_elsewhere:
            return self.accounts_elsewhere[0].resolve_unclaimed()
        else:
            return None

    def resolve_unclaimed(self):
        """Given a username, return an URL path.
        """
        rec = gittip.db.one_or_zero( "SELECT platform, user_info "
                                     "FROM elsewhere "
                                     "WHERE participant = %s"
                                   , (self.username,)
                                    )
        if rec is None:
            out = None
        elif rec['platform'] == 'github':
            out = '/on/github/%s/' % rec['user_info']['login']
        else:
            assert rec['platform'] == 'twitter'
            out = '/on/twitter/%s/' % rec['user_info']['screen_name']
        return out


    # XXX

    def set_as_claimed(self, claimed_at=None):
        if claimed_at is None:
            claimed_at = datetime.datetime.now(pytz.utc)
        self.claimed_time = claimed_at
        db.session.add(self)
        db.session.commit()

    def set_as_claimed(self):
        CLAIM = """\

            UPDATE participants
               SET claimed_time=CURRENT_TIMESTAMP
             WHERE username=%s
               AND claimed_time IS NULL

        """
        gittip.db.run(CLAIM, (self.username,))




    def insert_into_communities(self, is_member, name, slug):
        username = self.username
        gittip.db.run("""

            INSERT INTO communities
                        (ctime, name, slug, participant, is_member)
                 VALUES ( COALESCE (( SELECT ctime
                                        FROM communities
                                       WHERE (participant=%s AND slug=%s)
                                       LIMIT 1
                                      ), CURRENT_TIMESTAMP)
                        , %s, %s, %s, %s
                         )
              RETURNING ( SELECT count(*) = 0
                            FROM communities
                           WHERE participant=%s
                         )
                     AS first_time_community

        """, (username, slug, name, slug, username, is_member, username))

    def change_username(self, suggested):
        """Raise Response or return None.

        We want to be pretty loose with usernames. Unicode is allowed--XXX
        aspen bug :(. So are spaces.Control characters aren't. We also limit to
        32 characters in length.

        """
        for i, c in enumerate(suggested):
            if i == 32:
                raise self.UsernameTooLong  # Request Entity Too Large (more or less)
            elif ord(c) < 128 and c not in ASCII_ALLOWED_IN_USERNAME:
                raise self.UsernameContainsInvalidCharacters  # Yeah, no.
            elif c not in ASCII_ALLOWED_IN_USERNAME:
                # XXX Burned by an Aspen bug. :`-(
                # https://github.com/gittip/aspen/issues/102
                raise self.UsernameContainsInvalidCharacters

        lowercased = suggested.lower()

        if lowercased in gittip.RESTRICTED_USERNAMES:
            raise self.UsernameIsRestricted

        if suggested != self.username:
            # Will raise IntegrityError if the desired username is taken.
            rec = gittip.db.one_or_zero( "UPDATE participants "
                                         "SET username=%s WHERE username=%s "
                                         "RETURNING username"
                                       , (suggested, self.username)
                                        )

            assert rec is not None               # sanity check
            assert suggested == rec['username']  # sanity check
            self.username = suggested


    # XXX

    def get_accounts_elsewhere(self):
        github_account = twitter_account = bitbucket_account = \
                                                    bountysource_account = None
        for account in self.accounts_elsewhere.all():
            if account.platform == "github":
                github_account = account
            elif account.platform == "twitter":
                twitter_account = account
            elif account.platform == "bitbucket":
                bitbucket_account = account
            elif account.platform == "bountysource":
                bountysource_account = account
            else:
                raise self.UnknownPlatform(account.platform)
        return ( github_account
               , twitter_account
               , bitbucket_account
               , bountysource_account
                )

    def get_accounts_elsewhere(self):
        """Return a two-tuple of elsewhere dicts.
        """
        ACCOUNTS = """
            SELECT * FROM elsewhere WHERE participant=%s;
        """
        accounts = gittip.db.all(ACCOUNTS, (self.username,))
        assert accounts is not None
        twitter_account = None
        github_account = None
        for account in accounts:
            if account['platform'] == 'github':
                github_account = account
            else:
                assert account['platform'] == 'twitter', account['platform']
                twitter_account = account
        return (github_account, twitter_account)

    def get_img_src(self, size=128):
        """Return a value for <img src="..." />.

        Until we have our own profile pics, delegate. XXX Is this an attack
        vector? Can someone inject this value? Don't think so, but if you make
        it happen, let me know, eh? Thanks. :)

            https://www.gittip.com/security.txt

        """
        typecheck(size, int)

        src = '/assets/%s/avatar-default.gif' % os.environ['__VERSION__']

        github, twitter, bitbucket, bountysource = self.get_accounts_elsewhere()
        if github is not None:
            # GitHub -> Gravatar: http://en.gravatar.com/site/implement/images/
            if 'gravatar_id' in github.user_info:
                gravatar_hash = github.user_info['gravatar_id']
                src = "https://www.gravatar.com/avatar/%s.jpg?s=%s"
                src %= (gravatar_hash, size)

        elif twitter is not None:
            # https://dev.twitter.com/docs/api/1.1/get/users/show
            if 'profile_image_url_https' in twitter.user_info:
                src = twitter.user_info['profile_image_url_https']

                # For Twitter, we don't have good control over size. The
                # biggest option is 73px(?!), but that's too small. Let's go
                # with the original: even though it may be huge, that's
                # preferrable to guaranteed blurriness. :-/

                src = src.replace('_normal.', '.')

        return src




    def set_tip_to(self, tippee, amount):
        """Given participant id and amount as str, return a tuple.

        We INSERT instead of UPDATE, so that we have history to explore. The
        COALESCE function returns the first of its arguments that is not NULL.
        The effect here is to stamp all tips with the timestamp of the first
        tip from this user to that. I believe this is used to determine the
        order of transfers during payday.

        The tuple returned is the amount as a Decimal and a boolean indicating
        whether this is the first time this tipper has tipped (we want to track
        that as part of our conversion funnel).

        """

        if self.username == tippee:
            raise self.NoSelfTipping

        amount = Decimal(amount)  # May raise InvalidOperation
        if (amount < gittip.MIN_TIP) or (amount > gittip.MAX_TIP):
            raise self.BadAmount

        NEW_TIP = """\

            INSERT INTO tips
                        (ctime, tipper, tippee, amount)
                 VALUES ( COALESCE (( SELECT ctime
                                        FROM tips
                                       WHERE (tipper=%s AND tippee=%s)
                                       LIMIT 1
                                      ), CURRENT_TIMESTAMP)
                        , %s, %s, %s
                         )
              RETURNING ( SELECT count(*) = 0 FROM tips WHERE tipper=%s )
                     AS first_time_tipper

        """
        args = (self.username, tippee, self.username, tippee, amount, \
                                                                 self.username)
        first_time_tipper = \
                      gittip.db.one_or_zero(NEW_TIP, args)['first_time_tipper']
        return amount, first_time_tipper


    # XXX

    def get_tip_to(self, tippee):
        tip = self.tips_giving.filter_by(tippee=tippee).first()

        if tip:
            amount = tip.amount
        else:
            amount = Decimal('0.00')

        return amount

    def get_tip_to(self, tippee):
        """Given two user ids, return a Decimal.
        """
        TIP = """\

            SELECT amount
              FROM tips
             WHERE tipper=%s
               AND tippee=%s
          ORDER BY mtime DESC
             LIMIT 1

        """
        rec = gittip.db.one_or_zero(TIP, (self.username, tippee))
        if rec is None:
            tip = Decimal('0.00')
        else:
            tip = rec['amount']
        return tip



    # XXX

    def get_dollars_receiving(self):
        return sum(tip.amount for tip in self.valid_tips_receiving) + Decimal('0.00')
    def get_dollars_receiving(self):
        """Return a Decimal.
        """

        BACKED = """\

            SELECT sum(amount) AS dollars_receiving
              FROM ( SELECT DISTINCT ON (tipper)
                            amount
                          , tipper
                       FROM tips
                       JOIN participants p ON p.username = tipper
                      WHERE tippee=%s
                        AND last_bill_result = ''
                        AND is_suspicious IS NOT true
                   ORDER BY tipper
                          , mtime DESC
                    ) AS foo

        """
        rec = gittip.db.one_or_zero(BACKED, (self.username,))
        if rec is None:
            amount = None
        else:
            amount = rec['dollars_receiving']  # might be None

        if amount is None:
            amount = Decimal('0.00')

        return amount


    def get_dollars_giving(self):
        """Return a Decimal.
        """

        BACKED = """\

            SELECT sum(amount) AS dollars_giving
              FROM ( SELECT DISTINCT ON (tippee)
                            amount
                          , tippee
                       FROM tips
                       JOIN participants p ON p.username = tippee
                      WHERE tipper=%s
                        AND is_suspicious IS NOT true
                        AND claimed_time IS NOT NULL
                   ORDER BY tippee
                          , mtime DESC
                    ) AS foo

        """
        rec = gittip.db.one_or_zero(BACKED, (self.username,))
        if rec is None:
            amount = None
        else:
            amount = rec['dollars_giving']  # might be None

        if amount is None:
            amount = Decimal('0.00')

        return amount


    def get_number_of_backers(self):
        """Given a unicode, return an int.
        """

        BACKED = """\

            SELECT count(amount) AS nbackers
              FROM ( SELECT DISTINCT ON (tipper)
                            amount
                          , tipper
                       FROM tips
                       JOIN participants p ON p.username = tipper
                      WHERE tippee=%s
                        AND last_bill_result = ''
                        AND is_suspicious IS NOT true
                   ORDER BY tipper
                          , mtime DESC
                    ) AS foo
             WHERE amount > 0

        """
        rec = gittip.db.one_or_zero(BACKED, (self.username,))
        if rec is None:
            nbackers = None
        else:
            nbackers = rec['nbackers']  # might be None

        if nbackers is None:
            nbackers = 0

        return nbackers


    def get_tip_distribution(self):
        """
            Returns a data structure in the form of:
            [
                [TIPAMOUNT1, TIPAMOUNT2...TIPAMOUNTN],
                total_number_patrons_giving_to_me,
                total_amount_received
            ]

            where each TIPAMOUNTN is in the form:

            [amount,
             number_of_tippers_for_this_amount,
             total_amount_given_at_this_amount,
             proportion_of_tips_at_this_amount,
             proportion_of_total_amount_at_this_amount
            ]

        """
        SQL = """

            SELECT amount
                 , count(amount) AS ncontributing
              FROM ( SELECT DISTINCT ON (tipper)
                            amount
                          , tipper
                       FROM tips
                       JOIN participants p ON p.username = tipper
                      WHERE tippee=%s
                        AND last_bill_result = ''
                        AND is_suspicious IS NOT true
                   ORDER BY tipper
                          , mtime DESC
                    ) AS foo
             WHERE amount > 0
          GROUP BY amount
          ORDER BY amount

        """

        tip_amounts = []

        npatrons = 0.0  # float to trigger float division
        contributed = Decimal('0.00')
        for rec in gittip.db.all(SQL, (self.username,)):
            tip_amounts.append([ rec['amount']
                       , rec['ncontributing']
                       , rec['amount'] * rec['ncontributing']
                        ])
            contributed += tip_amounts[-1][2]
            npatrons += rec['ncontributing']

        for row in tip_amounts:
            row.append((row[1] / npatrons) if npatrons > 0 else 0)
            row.append((row[2] / contributed) if contributed > 0 else 0)

        return tip_amounts, npatrons, contributed


    def get_giving_for_profile(self, db=None):
        """Given a participant id and a date, return a list and a Decimal.

        This function is used to populate a participant's page for their own
        viewing pleasure.

        A half-injected dependency, that's what db is.

        """
        if db is None:
            from gittip import db

        TIPS = """\

            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , p.claimed_time
                     , p.username_lower
                  FROM tips t
                  JOIN participants p ON p.username = t.tippee
                 WHERE tipper = %s
                   AND p.is_suspicious IS NOT true
                   AND p.claimed_time IS NOT NULL
              ORDER BY tippee
                     , t.mtime DESC
            ) AS foo
            ORDER BY amount DESC
                   , username_lower

        """
        tips = db.all(TIPS, (self.username,))

        UNCLAIMED_TIPS = """\

            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , p.claimed_time
                     , e.platform
                     , e.user_info
                  FROM tips t
                  JOIN participants p ON p.username = t.tippee
                  JOIN elsewhere e ON e.participant = t.tippee
                 WHERE tipper = %s
                   AND p.is_suspicious IS NOT true
                   AND p.claimed_time IS NULL
              ORDER BY tippee
                     , t.mtime DESC
            ) AS foo
            ORDER BY amount DESC
                   , lower(user_info->'screen_name')
                   , lower(user_info->'username')
                   , lower(user_info->'login')

        """
        unclaimed_tips = db.all(UNCLAIMED_TIPS, (self.username,))


        # Compute the total.
        # ==================
        # For payday we only want to process payments to tippees who have
        # themselves opted into Gittip. For the tipper's profile page we want
        # to show the total amount they've pledged (so they're not surprised
        # when someone *does* start accepting tips and all of a sudden they're
        # hit with bigger charges.

        total = sum([t['amount'] for t in tips])
        if not total:
            # If tips is an empty list, total is int 0. We want a Decimal.
            total = Decimal('0.00')

        unclaimed_total = sum([t['amount'] for t in unclaimed_tips])
        if not unclaimed_total:
            unclaimed_total = Decimal('0.00')

        return tips, total, unclaimed_tips, unclaimed_total


    def get_tips_and_total(self, for_payday=False, db=None):
        """Given a participant id and a date, return a list and a Decimal.

        This function is used by the payday function. If for_payday is not
        False it must be a date object. Originally we also used this function
        to populate the profile page, but our requirements there changed while,
        oddly, our requirements in payday *also* changed to match the old
        requirements of the profile page. So this function keeps the for_payday
        parameter after all.

        A half-injected dependency, that's what db is.

        """
        if db is None:
            from gittip import db

        if for_payday:

            # For payday we want the oldest relationship to be paid first.
            order_by = "ctime ASC"


            # This is where it gets crash-proof.
            # ==================================
            # We need to account for the fact that we may have crashed during
            # Payday and we're re-running that function. We only want to select
            # tips that existed before Payday started, but haven't been
            # processed as part of this Payday yet.
            #
            # It's a bug if the paydays subselect returns > 1 rows.
            #
            # XXX If we crash during Payday and we rerun it after a timezone
            # change, will we get burned? How?

            ts_filter = """\

                   AND mtime < %s
                   AND ( SELECT id
                           FROM transfers
                          WHERE tipper=t.tipper
                            AND tippee=t.tippee
                            AND timestamp >= %s
                        ) IS NULL

            """
            args = (self.username, for_payday, for_payday)
        else:
            order_by = "amount DESC"
            ts_filter = ""
            args = (self.username,)

        TIPS = """\

            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , p.claimed_time
                  FROM tips t
                  JOIN participants p ON p.username = t.tippee
                 WHERE tipper = %%s
                   AND p.is_suspicious IS NOT true
                   %s
              ORDER BY tippee
                     , t.mtime DESC
            ) AS foo
            ORDER BY %s
                   , tippee

        """ % (ts_filter, order_by)  # XXX, No injections here, right?!
        tips = db.all(TIPS, args)


        # Compute the total.
        # ==================
        # For payday we only want to process payments to tippees who have
        # themselves opted into Gittip. For the tipper's profile page we want
        # to show the total amount they've pledged (so they're not surprised
        # when someone *does* start accepting tips and all of a sudden they're
        # hit with bigger charges.

        if for_payday:
            to_total = [t for t in tips if t['claimed_time'] is not None]
        else:
            to_total = tips
        total = sum([t['amount'] for t in to_total])

        if not total:
            # If to_total is an empty list, total is int 0. We want a Decimal.
            total = Decimal('0.00')

        return tips, total


# Exceptions
# ==========

class ProblemChangingUsername(Exception): pass
class UsernameTooLong(ProblemChangingUsername): pass
class UsernameContainsInvalidCharacters(ProblemChangingUsername): pass
class UsernameIsRestricted(ProblemChangingUsername): pass
class UsernameAlreadyTaken(ProblemChangingUsername): pass

class UnknownPlatform(Exception): pass
class TooGreedy(Exception): pass
class MemberLimitReached(Exception): pass
class NoSelfTipping(Exception): pass
class BadAmount(Exception): pass


# Username Helpers
# ================

def gen_random_usernames():
    """Yield up to 100 random 12-hex-digit unicodes.

    We raise :py:exc:`StopIteration` after 100 usernames as a safety
    precaution.

    """
    seatbelt = 0
    while 1:
        yield hex(int(random.random() * 16**12))[2:].zfill(12).decode('ASCII')
        seatbelt += 1
        if seatbelt > 100:
            raise StopIteration


def reserve_a_random_username(txn):
    """Reserve a random username.

    :param txn: a :py:class:`psycopg2.cursor` managed as a :py:mod:`postgres` transaction
    :database: one ``INSERT`` on average
    :returns: a 12-hex-digit unicode
    :raises: :py:class:`StopIteration` if no acceptable username is found within 100 attempts

    The returned value is guaranteed to have been reserved in the database.

    """
    for username in gen_random_usernames():
        try:
            txn.execute( "INSERT INTO participants (username, username_lower) "
                         "VALUES (%s, %s)"
                       , (username, username.lower())
                        )
        except IntegrityError:  # Collision, try again with another value.
            pass
        else:
            break

    return username
