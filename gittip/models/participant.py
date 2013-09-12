"""*Participant* is the name Gittip gives to people and groups that are known
to Gittip. We've got a ``participants`` table in the database, and a
:py:class:`Participant` class that we define here. We distinguish several kinds
of participant, based on certain properties.

 - *Stub* participants
 - *Organizations* are plural participants
 - *Teams* are plural participants with members

"""
from __future__ import print_function, unicode_literals

import datetime
import random
import uuid
from decimal import Decimal

import gittip
import pytz
from aspen import Response
from aspen.utils import typecheck
from psycopg2 import IntegrityError
from postgres.orm import Model
from gittip.models._mixin_elsewhere import MixinElsewhere
from gittip.models._mixin_team import MixinTeam
from gittip.utils import canonicalize


ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                ".,-_:@ ")
NANSWERS_THRESHOLD = 0  # configured in wireup.py


class Participant(Model, MixinElsewhere, MixinTeam):
    """Represent a Gittip participant.
    """

    typname = 'participants'

    def __eq__(self, other):
        if not isinstance(other, Participant):
            return False
        return self.username == other.username

    def __ne__(self, other):
        if not isinstance(other, Participant):
            return False
        return self.username != other.username


    # Constructors
    # ============

    @classmethod
    def with_random_username(cls):
        """Return a new participant with a random username.
        """
        with cls.db.get_cursor() as cursor:
            username = reserve_a_random_username(cursor)
        return cls.from_username(username)

    @classmethod
    def from_id(cls, id):
        """Return an existing participant based on id.
        """
        return cls._from_thing("id", id)

    @classmethod
    def from_username(cls, username):
        """Return an existing participant based on username.
        """
        return cls._from_thing("username_lower", username.lower())

    @classmethod
    def from_session_token(cls, token):
        """Return an existing participant based on session token.
        """
        return cls._from_thing("session_token", token)

    @classmethod
    def from_api_key(cls, api_key):
        """Return an existing participant based on API key.
        """
        return cls._from_thing("api_key", api_key)

    @classmethod
    def _from_thing(cls, thing, value):
        assert thing in ("id", "username_lower", "session_token", "api_key")
        return cls.db.one("""

            SELECT participants.*::participants
              FROM participants
             WHERE {}=%s

        """.format(thing), (value,))


    # Session Management
    # ==================

    def start_new_session(self):
        """Set ``session_token`` in the database to a new uuid.

        :database: One UPDATE, one row

        """
        self._update_session_token(uuid.uuid4().hex)

    def end_session(self):
        """Set ``session_token`` in the database to ``NULL``.

        :database: One UPDATE, one row

        """
        self._update_session_token(None)

    def _update_session_token(self, new_token):
        self.db.run( "UPDATE participants SET session_token=%s "
                     "WHERE id=%s AND is_suspicious IS NOT true"
                   , (new_token, self.id,)
                    )
        self.set_attributes(session_token=new_token)

    def set_session_expires(self, expires):
        """Set session_expires in the database.

        :param float expires: A UNIX timestamp, which XXX we assume is UTC?
        :database: One UPDATE, one row

        """
        session_expires = datetime.datetime.fromtimestamp(expires) \
                                                      .replace(tzinfo=pytz.utc)
        self.db.run( "UPDATE participants SET session_expires=%s "
                     "WHERE id=%s AND is_suspicious IS NOT true"
                   , (session_expires, self.id,)
                    )
        self.set_attributes(session_expires=session_expires)


    # Number
    # ======

    @property
    def IS_SINGULAR(self):
        return self.number == 'singular'

    @property
    def IS_PLURAL(self):
        return self.number == 'plural'

    def update_number(self, number):
        assert number in ('singular', 'plural')
        self.db.run( "UPDATE participants SET number=%s WHERE id=%s"
                   , (number, self.id)
                    )
        self.set_attributes(number=number)


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

    def resolve_unclaimed(self):
        """Given a username, return an URL path.
        """
        rec = gittip.db.one( "SELECT platform, user_info "
                             "FROM elsewhere "
                             "WHERE participant = %s"
                           , (self.username,)
                            )
        if rec is None:
            out = None
        elif rec.platform == 'bitbucket':
            out = '/on/bitbucket/%s/' % rec.user_info['username']
        elif rec.platform == 'github':
            out = '/on/github/%s/' % rec.user_info['login']
        else:
            assert rec.platform == 'twitter'
            out = '/on/twitter/%s/' % rec.user_info['screen_name']
        return out

    def set_as_claimed(self):
        claimed_time = self.db.one("""\

            UPDATE participants
               SET claimed_time=CURRENT_TIMESTAMP
             WHERE username=%s
               AND claimed_time IS NULL
         RETURNING claimed_time

        """, (self.username,))
        self.set_attributes(claimed_time=claimed_time)



    # Random Junk
    # ===========

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

    @property
    def accepts_tips(self):
        return (self.goal is None) or (self.goal >= 0)


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
        
        Usernames are limited to alphanumeric characters, plus ".,-_:@ ",
        and can only be 32 characters long.

        """
        # TODO: reconsider allowing unicode usernames
        typecheck(suggested, unicode)

        if len(suggested) > 32:
            raise UsernameTooLong

        if set(suggested) - ASCII_ALLOWED_IN_USERNAME:
            raise UsernameContainsInvalidCharacters

        lowercased = suggested.lower()

        if lowercased in gittip.RESTRICTED_USERNAMES:
            raise UsernameIsRestricted

        if suggested != self.username:
            try:
                # Will raise IntegrityError if the desired username is taken.
                actual = gittip.db.one( "UPDATE participants "
                                        "SET username=%s, username_lower=%s "
                                        "WHERE username=%s "
                                        "RETURNING username, username_lower"
                                      , (suggested, lowercased, self.username)
                                      , back_as=tuple
                                       )
            except IntegrityError:
                raise UsernameAlreadyTaken(suggested)

            assert (suggested, lowercased) == actual  # sanity check
            self.set_attributes(username=suggested, username_lower=lowercased)


    def update_goal(self, goal):
        typecheck(goal, (Decimal, None))
        self.db.run( "UPDATE participants SET goal=%s WHERE username=%s"
                   , (goal, self.username)
                    )
        self.set_attributes(goal=goal)


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
            raise NoSelfTipping

        amount = Decimal(amount)  # May raise InvalidOperation
        if (amount < gittip.MIN_TIP) or (amount > gittip.MAX_TIP):
            raise BadAmount

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
        first_time_tipper = gittip.db.one(NEW_TIP, args)
        return amount, first_time_tipper


    def get_tip_to(self, tippee):
        """Given two user ids, return a Decimal.
        """
        return self.db.one("""\

            SELECT amount
              FROM tips
             WHERE tipper=%s
               AND tippee=%s
          ORDER BY mtime DESC
             LIMIT 1

        """, (self.username, tippee), default=Decimal('0.00'))


    def get_dollars_receiving(self):
        """Return a Decimal.
        """
        return self.db.one("""\

            SELECT sum(amount)
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

        """, (self.username,), default=Decimal('0.00'))


    def get_dollars_giving(self):
        """Return a Decimal.
        """
        return self.db.one("""\

            SELECT sum(amount)
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

        """, (self.username,), default=Decimal('0.00'))


    def get_number_of_backers(self):
        """Given a unicode, return an int.
        """
        return gittip.db.one("""\

            SELECT count(amount)
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

        """, (self.username,), default=0)


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
            tip_amounts.append([ rec.amount
                               , rec.ncontributing
                               , rec.amount * rec.ncontributing
                                ])
            contributed += tip_amounts[-1][2]
            npatrons += rec.ncontributing

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

        total = sum([t.amount for t in tips])
        if not total:
            # If tips is an empty list, total is int 0. We want a Decimal.
            total = Decimal('0.00')

        unclaimed_total = sum([t.amount for t in unclaimed_tips])
        if not unclaimed_total:
            unclaimed_total = Decimal('0.00')

        return tips, total, unclaimed_tips, unclaimed_total


    def get_tips_and_total(self, for_payday=False):
        """Given a participant id and a date, return a list and a Decimal.

        This function is used by the payday function. If for_payday is not
        False it must be a date object. Originally we also used this function
        to populate the profile page, but our requirements there changed while,
        oddly, our requirements in payday *also* changed to match the old
        requirements of the profile page. So this function keeps the for_payday
        parameter after all.

        """

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
        tips = self.db.all(TIPS, args, back_as=dict)


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


# Exceptions
# ==========

class ProblemChangingUsername(Exception):
    def __str__(self):
        return self.msg.format(self.args[0])

class UsernameTooLong(ProblemChangingUsername):
    msg = "The username '{}' is too long."

class UsernameContainsInvalidCharacters(ProblemChangingUsername):
    msg = "The username '{}' contains invalid characters."

class UsernameIsRestricted(ProblemChangingUsername):
    msg = "The username '{}' is restricted."

class UsernameAlreadyTaken(ProblemChangingUsername):
    msg = "The username '{}' is already taken."

class TooGreedy(Exception): pass
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

    :param txn: a :py:class:`psycopg2.cursor` managed as a :py:mod:`postgres`
        transaction
    :database: one ``INSERT`` on average
    :returns: a 12-hex-digit unicode
    :raises: :py:class:`StopIteration` if no acceptable username is found
        within 100 attempts

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


def typecast(request):
    """Given a Request, raise Response or return Participant.

    If user is not None then we'll restrict access to owners and admins.

    """

    # XXX We can't use this yet because we don't have an inbound Aspen hook
    # that fires after the first page of the simplate is exec'd.

    path = request.line.uri.path
    if 'username' not in path:
        return

    slug = path['username']

    participant = gittip.db.one( "SELECT participants.*::participants "
                                 "FROM participants "
                                 "WHERE username_lower=%s"
                               , (slug.lower())
                                )

    if participant is None:
        raise Response(404)

    canonicalize(request.line.uri.path.raw, '/', participant.username, slug)

    if participant.claimed_time is None:

        # This is a stub participant record for someone on another platform
        # who hasn't actually registered with Gittip yet. Let's bounce the
        # viewer over to the appropriate platform page.

        to = participant.resolve_unclaimed()
        if to is None:
            raise Response(404)
        request.redirect(to)

    path['participant'] = participant
