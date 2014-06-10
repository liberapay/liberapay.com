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
from decimal import Decimal, ROUND_DOWN
import uuid

import aspen
from aspen.utils import typecheck
from postgres.orm import Model
from psycopg2 import IntegrityError
import pytz

import gittip
from gittip import NotSane
from gittip.exceptions import (
    HasBigTips,
    UsernameIsEmpty,
    UsernameTooLong,
    UsernameContainsInvalidCharacters,
    UsernameIsRestricted,
    UsernameAlreadyTaken,
    NoSelfTipping,
    NoTippee,
    BadAmount,
)

from gittip.models import add_event
from gittip.models._mixin_team import MixinTeam
from gittip.models.account_elsewhere import AccountElsewhere
from gittip.utils.username import safely_reserve_a_username
from gittip import billing
from gittip.utils import is_card_expiring


ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                ".,-_:@ ")
# We use | in Sentry logging, so don't make that allowable. :-)

NANSWERS_THRESHOLD = 0  # configured in wireup.py

NOTIFIED_ABOUT_EXPIRATION = b'notifiedAboutExpiration'

class Participant(Model, MixinTeam):
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
            username = safely_reserve_a_username(cursor)
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
        participant = cls._from_thing("session_token", token)
        if participant and participant.session_expires < pytz.utc.localize(datetime.datetime.utcnow()):
            participant = None

        return participant

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


    # Claimed-ness
    # ============

    @property
    def is_claimed(self):
        return self.claimed_time is not None


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
        if number == 'singular':
            nbigtips = self.db.one("""\
                SELECT count(*) FROM current_tips WHERE tippee=%s AND amount > %s
            """, (self.username, gittip.MAX_TIP_SINGULAR))
            if nbigtips > 0:
                raise HasBigTips
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(action='set', id=self.id, values=dict(number=number)))
            c.execute( "UPDATE participants SET number=%s WHERE id=%s"
                     , (number, self.id)
                      )
        self.set_attributes(number=number)


    # Statement
    # =========

    def update_statement(self, statement):
        self.db.run("UPDATE participants SET statement=%s WHERE id=%s", (statement, self.id))
        self.set_attributes(statement=statement)


    # API Key
    # =======

    def recreate_api_key(self):
        api_key = str(uuid.uuid4())
        SQL = "UPDATE participants SET api_key=%s WHERE username=%s"
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(action='set', id=self.id, values=dict(api_key=api_key)))
            c.run(SQL, (api_key, self.username))
        return api_key


    # Claiming
    # ========
    # An unclaimed Participant is a stub that's created when someone pledges to
    # give to an AccountElsewhere that's not been connected on Gittip yet.

    def resolve_unclaimed(self):
        """Given a username, return an URL path.
        """
        rec = self.db.one( "SELECT platform, user_name "
                           "FROM elsewhere "
                           "WHERE participant = %s"
                           , (self.username,)
                            )
        if rec is None:
            return
        return '/on/%s/%s/' % (rec.platform, rec.user_name)

    def set_as_claimed(self):
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(id=self.id, action='claim'))
            claimed_time = c.one("""\

                UPDATE participants
                   SET claimed_time=CURRENT_TIMESTAMP
                 WHERE username=%s
                   AND claimed_time IS NULL
             RETURNING claimed_time

            """, (self.username,))
            self.set_attributes(claimed_time=claimed_time)


    # Canceling
    # =========

    class UnknownDisbursementStrategy(Exception): pass

    def cancel(self, disbursement_strategy):
        """Cancel the participant's account.
        """
        with self.db.get_cursor() as cursor:

            if disbursement_strategy == None:
                pass  # No balance, supposedly. archive will check.
            elif disbursement_strategy == 'bank':
                self.withdraw_balance_to_bank_account(cursor)
            elif disbursement_strategy == 'upstream':
                self.refund_to_patrons(cursor)
            elif disbursement_strategy == 'downstream':
                # This in particular needs to come before clear_tips_giving.
                self.distribute_balance_as_final_gift(cursor)
            else:
                raise self.UnknownDisbursementStrategy

            self.clear_tips_giving(cursor)
            self.clear_tips_receiving(cursor)
            self.clear_personal_information(cursor)

            return self.archive(cursor)


    class NotWhitelisted(Exception): pass
    class NoBalancedCustomerHref(Exception): pass

    def withdraw_balance_to_bank_account(self, cursor):
        if self.is_suspicious in (True, None):
            raise self.NotWhitelisted
        if self.balanced_customer_href is None:
            raise self.NoBalancedCustomerHref

        from gittip.billing.payday import Payday
        hack = Payday(self.db)  # Our payout code is on the Payday object. Rather than
                                # refactor right now, let's just use it from there.

        # Monkey-patch a couple methods, coopting them for callbacks, essentially.
        hack.mark_ach_failed = lambda cursor: None
        hack.mark_ach_success = lambda cursor, amount, fee: self.set_attributes(balance=0)

        hack.ach_credit( ts_start=None                  # not used
                       , participant=self
                       , tips=None                      # not used
                       , total=Decimal('0.00')          # don't withold anything
                       , minimum_credit=Decimal('0.00') # send it all
                        ) # XXX Records the exchange using a different cursor. :-/


    def refund_balance_to_patrons(self, cursor):
        raise NotImplementedError


    class NoOneToGiveFinalGiftTo(Exception): pass

    def distribute_balance_as_final_gift(self, cursor):
        """Distribute a balance as a final gift.
        """
        if self.balance == 0:
            return

        claimed_tips, claimed_total, _, _= self.get_giving_for_profile()
        transfers = []
        distributed = Decimal('0.00')

        for tip in claimed_tips:
            if tip.amount == 0:
                continue
            rate = tip.amount / claimed_total
            pro_rated = (self.balance * rate).quantize(Decimal('0.01'), ROUND_DOWN)
            distributed += pro_rated
            transfers.append([tip.tippee, pro_rated])

        if not transfers:
            raise self.NoOneToGiveFinalGiftTo

        diff = self.balance - distributed
        if diff != 0:
            transfers[0][1] += diff  # Give it to the highest receiver.

        for tippee, amount in transfers:
            assert amount > 0
            balance = cursor.one( "UPDATE participants SET balance=balance - %s "
                                  "WHERE username=%s RETURNING balance"
                                , (amount, self.username)
                                 )
            assert balance >= 0  # sanity check
            cursor.run( "UPDATE participants SET balance=balance + %s WHERE username=%s"
                      , (amount, tippee)
                       )
            cursor.run( "INSERT INTO transfers (tipper, tippee, amount) VALUES (%s, %s, %s)"
                      , (self.username, tippee, amount)
                       )

        assert balance == 0
        self.set_attributes(balance=balance)


    def clear_tips_giving(self, cursor):
        """Zero out tips from a given user.
        """
        tippees = cursor.all("""

            SELECT ( SELECT participants.*::participants
                       FROM participants
                      WHERE username=tippee
                    ) AS tippee
              FROM current_tips
             WHERE tipper = %s
               AND amount > 0

        """, (self.username,))
        for tippee in tippees:
            self.set_tip_to(tippee, '0.00', cursor=cursor)

    def clear_tips_receiving(self, cursor):
        """Zero out tips to a given user. This is a workaround for #1469.
        """
        tippers = cursor.all("""

            SELECT ( SELECT participants.*::participants
                       FROM participants
                      WHERE username=tipper
                    ) AS tipper
              FROM current_tips
             WHERE tippee = %s
               AND amount > 0

        """, (self.username,))
        for tipper in tippers:
            tipper.set_tip_to(self, '0.00', cursor=cursor)


    def clear_personal_information(self, cursor):
        """Clear personal information such as statement and goal.
        """
        cursor.run("""

            UPDATE participants
               SET statement=''
                 , goal=NULL
                 , anonymous_giving=False
                 , anonymous_receiving=False
                 , number='singular'
                 , avatar_url=NULL
                 , email=NULL
            WHERE username=%s

        """, (self.username,))
        self.set_attributes( statement=''
                           , goal=None
                           , anonymous_giving=False
                           , anonymous_receiving=False
                           , number='singular'
                           , avatar_url=None
                           , email=None
                            )


    # Random Junk
    # ===========

    def get_teams(self):
        """Return a list of teams this user is a member of.
        """
        return self.db.all("""

            SELECT team AS name
                 , ( SELECT count(*)
                       FROM current_takes
                      WHERE team=x.team
                    ) AS nmembers
              FROM current_takes x
             WHERE member=%s;

        """, (self.username,))

    @property
    def accepts_tips(self):
        return (self.goal is None) or (self.goal >= 0)


    def insert_into_communities(self, is_member, name, slug):
        username = self.username
        self.db.run("""

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
        suggested = suggested.strip()

        if not suggested:
            raise UsernameIsEmpty(suggested)

        if len(suggested) > 32:
            raise UsernameTooLong(suggested)

        if set(suggested) - ASCII_ALLOWED_IN_USERNAME:
            raise UsernameContainsInvalidCharacters(suggested)

        lowercased = suggested.lower()

        if lowercased in gittip.RESTRICTED_USERNAMES:
            raise UsernameIsRestricted(suggested)

        if suggested != self.username:
            try:
                # Will raise IntegrityError if the desired username is taken.
                with self.db.get_cursor(back_as=tuple) as c:
                    add_event(c, 'participant', dict(id=self.id, action='set', values=dict(username=suggested)))
                    actual = c.one( "UPDATE participants "
                                    "SET username=%s, username_lower=%s "
                                    "WHERE username=%s "
                                    "RETURNING username, username_lower"
                                   , (suggested, lowercased, self.username)
                                   )
            except IntegrityError:
                raise UsernameAlreadyTaken(suggested)

            assert (suggested, lowercased) == actual # sanity check
            self.set_attributes(username=suggested, username_lower=lowercased)

        return suggested

    def update_avatar(self):
        avatar_url = self.db.run("""
            UPDATE participants p
               SET avatar_url = (
                       SELECT avatar_url
                         FROM elsewhere
                        WHERE participant = p.username
                     ORDER BY platform = 'github' DESC,
                              avatar_url LIKE '%%gravatar.com%%' DESC
                        LIMIT 1
                   )
             WHERE p.username = %s
         RETURNING avatar_url
        """, (self.username,))
        self.set_attributes(avatar_url=avatar_url)

    def update_email(self, email, confirmed=False):
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(id=self.id, action='set', values=dict(current_email=email)))
            c.one("UPDATE participants SET email = ROW(%s, %s) WHERE username=%s RETURNING id"
                 , (email, confirmed, self.username)
                  )
        self.set_attributes(email=(email, confirmed))

    def update_goal(self, goal):
        typecheck(goal, (Decimal, None))
        with self.db.get_cursor() as c:
            tmp = goal if goal is None else unicode(goal)
            add_event(c, 'participant', dict(id=self.id, action='set', values=dict(goal=tmp)))
            c.one( "UPDATE participants SET goal=%s WHERE username=%s RETURNING id"
                 , (goal, self.username)
                  )
        self.set_attributes(goal=goal)


    def set_tip_to(self, tippee, amount, cursor=None):
        """Given a Participant or username, and amount as str, return a tuple.

        We INSERT instead of UPDATE, so that we have history to explore. The
        COALESCE function returns the first of its arguments that is not NULL.
        The effect here is to stamp all tips with the timestamp of the first
        tip from this user to that. I believe this is used to determine the
        order of transfers during payday.

        The tuple returned is the amount as a Decimal and a boolean indicating
        whether this is the first time this tipper has tipped (we want to track
        that as part of our conversion funnel).

        """
        if not isinstance(tippee, Participant):
            tippee, u = Participant.from_username(tippee), tippee
            if not tippee:
                raise NoTippee(u)

        if self.username == tippee.username:
            raise NoSelfTipping

        amount = Decimal(amount)  # May raise InvalidOperation
        max_tip = gittip.MAX_TIP_PLURAL if tippee.IS_PLURAL else gittip.MAX_TIP_SINGULAR
        if (amount < gittip.MIN_TIP) or (amount > max_tip):
            raise BadAmount

        NEW_TIP = """\

            INSERT INTO tips
                        (ctime, tipper, tippee, amount)
                 VALUES ( COALESCE (( SELECT ctime
                                        FROM tips
                                       WHERE (tipper=%(tipper)s AND tippee=%(tippee)s)
                                       LIMIT 1
                                      ), CURRENT_TIMESTAMP)
                        , %(tipper)s, %(tippee)s, %(amount)s
                         )
              RETURNING ( SELECT count(*) = 0 FROM tips WHERE tipper=%(tipper)s )
                     AS first_time_tipper

        """
        args = dict(tipper=self.username, tippee=tippee.username, amount=amount)
        first_time_tipper = (cursor or self.db).one(NEW_TIP, args)
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
        return self.db.one("""\

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
            Returns a data structure in the form of::

                [
                    [TIPAMOUNT1, TIPAMOUNT2...TIPAMOUNTN],
                    total_number_patrons_giving_to_me,
                    total_amount_received
                ]

            where each TIPAMOUNTN is in the form::

                [
                    amount,
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
        for rec in self.db.all(SQL, (self.username,)):
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


    def get_giving_for_profile(self):
        """Given a participant id and a date, return a list and a Decimal.

        This function is used to populate a participant's page for their own
        viewing pleasure.

        """

        TIPS = """\

            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , p.claimed_time
                     , p.username_lower
                     , p.number
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
        tips = self.db.all(TIPS, (self.username,))

        UNCLAIMED_TIPS = """\

            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , p.claimed_time
                     , e.platform
                     , e.user_name
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
                   , lower(user_name)

        """
        unclaimed_tips = self.db.all(UNCLAIMED_TIPS, (self.username,))


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
        total = sum([t['amount'] for t in to_total], Decimal('0.00'))

        return tips, total


    def get_og_title(self):
        out = self.username
        receiving = self.get_dollars_receiving()
        giving = self.get_dollars_giving()
        if (giving > receiving) and not self.anonymous_giving:
            out += " gives $%.2f/wk" % giving
        elif receiving > 0 and not self.anonymous_receiving:
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


    def get_accounts_elsewhere(self):
        """Return a dict of AccountElsewhere instances.
        """
        accounts = self.db.all("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE participant=%s

        """, (self.username,))
        accounts_dict = {account.platform: account for account in accounts}
        return accounts_dict


    class StillReceivingTips(Exception): pass
    class BalanceIsNotZero(Exception): pass

    def archive(self, cursor):
        """Given a cursor, use it to archive ourself.

        Archiving means changing to a random username so the username they were
        using is released. We also sign them out.

        """

        # Sanity-check that balance and tips have been dealt with.
        # ========================================================

        INCOMING = "SELECT count(*) FROM current_tips WHERE tippee = %s AND amount > 0"
        if cursor.one(INCOMING, (self.username,)) > 0:
            raise self.StillReceivingTips

        if self.balance != 0:
            raise self.BalanceIsNotZero


        # Do it!
        # ======

        def reserve(cursor, username):
            check = cursor.one("""

                UPDATE participants
                   SET username=%s
                     , username_lower=%s
                     , claimed_time=NULL
                     , session_token=NULL
                     , session_expires=now()
                 WHERE username=%s
             RETURNING username

            """, ( username
                 , username.lower()
                 , self.username
                  ), default=NotSane)
            return check

        archived_as = safely_reserve_a_username(cursor, reserve=reserve)
        add_event(cursor, 'participant', dict( id=self.id
                                             , action='archive'
                                             , values=dict( new_username=archived_as
                                                          , old_username=self.username
                                                           )
                                              ))
        return archived_as


    def take_over(self, account, have_confirmation=False):
        """Given an AccountElsewhere or a tuple (platform_name, user_id),
        associate an elsewhere account.

        Returns None or raises NeedConfirmation.

        This method associates an account on another platform (GitHub, Twitter,
        etc.) with the given Gittip participant. Every account elsewhere has an
        associated Gittip participant account, even if its only a stub
        participant (it allows us to track pledges to that account should they
        ever decide to join Gittip).

        In certain circumstances, we want to present the user with a
        confirmation before proceeding to transfer the account elsewhere to
        the new Gittip account; NeedConfirmation is the signal to request
        confirmation. If it was the last account elsewhere connected to the old
        Gittip account, then we absorb the old Gittip account into the new one,
        effectively archiving the old account.

        Here's what absorbing means:

            - consolidated tips to and fro are set up for the new participant

                Amounts are summed, so if alice tips bob $1 and carl $1, and
                then bob absorbs carl, then alice tips bob $2(!) and carl $0.

                And if bob tips alice $1 and carl tips alice $1, and then bob
                absorbs carl, then bob tips alice $2(!) and carl tips alice $0.

                The ctime of each new consolidated tip is the older of the two
                tips that are being consolidated.

                If alice tips bob $1, and alice absorbs bob, then alice tips
                bob $0.

                If alice tips bob $1, and bob absorbs alice, then alice tips
                bob $0.

            - all tips to and from the other participant are set to zero
            - the absorbed username is released for reuse
            - the absorption is recorded in an absorptions table

        This is done in one transaction.
        """

        if isinstance(account, AccountElsewhere):
            platform, user_id = account.platform, account.user_id
        else:
            platform, user_id = account

        CREATE_TEMP_TABLE_FOR_UNIQUE_TIPS = """

        CREATE TEMP TABLE __temp_unique_tips ON COMMIT drop AS

            -- Get all the latest tips from everyone to everyone.

            SELECT DISTINCT ON (tipper, tippee)
                   ctime, tipper, tippee, amount
              FROM tips
          ORDER BY tipper, tippee, mtime DESC;

        """

        CONSOLIDATE_TIPS_RECEIVING = """

            -- Create a new set of tips, one for each current tip *to* either
            -- the dead or the live account. If a user was tipping both the
            -- dead and the live account, then we create one new combined tip
            -- to the live account (via the GROUP BY and sum()).

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), tipper, %(live)s AS tippee, sum(amount)

                   FROM __temp_unique_tips

                  WHERE (tippee = %(dead)s OR tippee = %(live)s)
                        -- Include tips *to* either the dead or live account.

                AND NOT (tipper = %(dead)s OR tipper = %(live)s)
                        -- Don't include tips *from* the dead or live account,
                        -- lest we convert cross-tipping to self-tipping.

                    AND amount > 0
                        -- Don't include zeroed out tips, so we avoid a no-op
                        -- zero tip entry.

               GROUP BY tipper

        """

        CONSOLIDATE_TIPS_GIVING = """

            -- Create a new set of tips, one for each current tip *from* either
            -- the dead or the live account. If both the dead and the live
            -- account were tipping a given user, then we create one new
            -- combined tip from the live account (via the GROUP BY and sum()).

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), %(live)s AS tipper, tippee, sum(amount)

                   FROM __temp_unique_tips

                  WHERE (tipper = %(dead)s OR tipper = %(live)s)
                        -- Include tips *from* either the dead or live account.

                AND NOT (tippee = %(dead)s OR tippee = %(live)s)
                        -- Don't include tips *to* the dead or live account,
                        -- lest we convert cross-tipping to self-tipping.

                    AND amount > 0
                        -- Don't include zeroed out tips, so we avoid a no-op
                        -- zero tip entry.

               GROUP BY tippee

        """

        ZERO_OUT_OLD_TIPS_RECEIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM __temp_unique_tips
                 WHERE tippee=%s AND amount > 0

        """

        ZERO_OUT_OLD_TIPS_GIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM __temp_unique_tips
                 WHERE tipper=%s AND amount > 0

        """

        with self.db.get_cursor() as cursor:

            # Load the existing connection.
            # =============================
            # Every account elsewhere has at least a stub participant account
            # on Gittip.

            elsewhere = cursor.one("""

                SELECT elsewhere.*::elsewhere_with_participant
                  FROM elsewhere
                  JOIN participants ON participant=participants.username
                 WHERE elsewhere.platform=%s AND elsewhere.user_id=%s

            """, (platform, user_id), default=NotSane)
            other = elsewhere.participant


            if self.username == other.username:
                # this is a no op - trying to take over itself
                return


            # Make sure we have user confirmation if needed.
            # ==============================================
            # We need confirmation in whatever combination of the following
            # three cases:
            #
            #   - the other participant is not a stub; we are taking the
            #       account elsewhere away from another viable Gittip
            #       participant
            #
            #   - the other participant has no other accounts elsewhere; taking
            #       away the account elsewhere will leave the other Gittip
            #       participant without any means of logging in, and it will be
            #       archived and its tips absorbed by us
            #
            #   - we already have an account elsewhere connected from the given
            #       platform, and it will be handed off to a new stub
            #       participant

            # other_is_a_real_participant
            other_is_a_real_participant = other.is_claimed

            # this_is_others_last_account_elsewhere
            nelsewhere = cursor.one( "SELECT count(*) FROM elsewhere "
                                     "WHERE participant=%s"
                                   , (other.username,)
                                    )
            assert nelsewhere > 0           # sanity check
            this_is_others_last_account_elsewhere = (nelsewhere == 1)

            # we_already_have_that_kind_of_account
            nparticipants = cursor.one( "SELECT count(*) FROM elsewhere "
                                        "WHERE participant=%s AND platform=%s"
                                      , (self.username, platform)
                                       )
            assert nparticipants in (0, 1)  # sanity check
            we_already_have_that_kind_of_account = nparticipants == 1

            if elsewhere.is_team and we_already_have_that_kind_of_account:
                if len(self.get_accounts_elsewhere()) == 1:
                    raise TeamCantBeOnlyAuth

            need_confirmation = NeedConfirmation( other_is_a_real_participant
                                                , this_is_others_last_account_elsewhere
                                                , we_already_have_that_kind_of_account
                                                 )
            if need_confirmation and not have_confirmation:
                raise need_confirmation


            # We have user confirmation. Proceed.
            # ===================================
            # There is a race condition here. The last person to call this will
            # win. XXX: I'm not sure what will happen to the DB and UI for the
            # loser.


            # Move any old account out of the way.
            # ====================================

            if we_already_have_that_kind_of_account:
                new_stub_username = safely_reserve_a_username(cursor)
                cursor.run( "UPDATE elsewhere SET participant=%s "
                            "WHERE platform=%s AND participant=%s"
                          , (new_stub_username, platform, self.username)
                           )


            # Do the deal.
            # ============
            # If other_is_not_a_stub, then other will have the account
            # elsewhere taken away from them with this call. If there are other
            # browsing sessions open from that account, they will stay open
            # until they expire (XXX Is that okay?)

            cursor.run( "UPDATE elsewhere SET participant=%s "
                        "WHERE platform=%s AND user_id=%s"
                      , (self.username, platform, user_id)
                       )


            # Fold the old participant into the new as appropriate.
            # =====================================================
            # We want to do this whether or not other is a stub participant.

            if this_is_others_last_account_elsewhere:

                # Take over tips.
                # ===============

                x, y = self.username, other.username
                cursor.run(CREATE_TEMP_TABLE_FOR_UNIQUE_TIPS)
                cursor.run(CONSOLIDATE_TIPS_RECEIVING, dict(live=x, dead=y))
                cursor.run(CONSOLIDATE_TIPS_GIVING, dict(live=x, dead=y))
                cursor.run(ZERO_OUT_OLD_TIPS_RECEIVING, (other.username,))
                cursor.run(ZERO_OUT_OLD_TIPS_GIVING, (other.username,))


                # Archive the old participant.
                # ============================
                # We always give them a new, random username. We sign out
                # the old participant.

                archive_username = other.archive(cursor)


                # Record the absorption.
                # ======================
                # This is for preservation of history.

                cursor.run( "INSERT INTO absorptions "
                            "(absorbed_was, absorbed_by, archived_as) "
                            "VALUES (%s, %s, %s)"
                          , ( other.username
                            , self.username
                            , archive_username
                             )
                           )

        self.update_avatar()

    def delete_elsewhere(self, platform, user_id):
        """Deletes account elsewhere unless the user would not be able
        to log in anymore.
        """
        user_id = unicode(user_id)
        with self.db.get_cursor() as c:
            accounts = c.all("""
                SELECT platform, user_id
                  FROM elsewhere
                 WHERE participant=%s
                   AND platform IN %s
                   AND NOT is_team
            """, (self.username, AccountElsewhere.signin_platforms_names))
            assert len(accounts) > 0
            if len(accounts) == 1 and accounts[0] == (platform, user_id):
                raise LastElsewhere()
            c.one("""
                DELETE FROM elsewhere
                WHERE participant=%s
                AND platform=%s
                AND user_id=%s
                RETURNING participant
            """, (self.username, platform, user_id), default=NonexistingElsewhere)
            add_event(c, 'participant', dict(id=self.id, action='disconnect', values=dict(platform=platform, user_id=user_id)))
        self.update_avatar()

    def credit_card_expiring(self, request, response):

        if NOTIFIED_ABOUT_EXPIRATION in request.headers.cookie:
            cookie = request.headers.cookie[NOTIFIED_ABOUT_EXPIRATION]
            if cookie.value == self.session_token:
                return False

        try:
            if self.balanced_customer_href:
                card = billing.BalancedCard(self.balanced_customer_href)
            elif self.stripe_customer_id:
                card = billing.StripeCard(self.stripe_customer_id)
            else:
                return False
            year, month = card['expiration_year'], card['expiration_month']
            if not (year and month):
                return False
            card_expiring = is_card_expiring(int(year), int(month))
            response.headers.cookie[NOTIFIED_ABOUT_EXPIRATION] = self.session_token
            return card_expiring
        except Exception as e:
            if request.website.env.testing:
                raise
            aspen.log(e)
            request.website.tell_sentry(e, request)
            return False

    def to_dict(self, details=False, inquirer=None):
        output = { 'id': self.id
                 , 'username': self.username
                 , 'avatar': self.avatar_url
                 , 'number': self.number
                 , 'on': 'gittip'
                 }

        if not details:
            return output

        # Key: npatrons
        output['npatrons'] = self.get_number_of_backers()

        # Key: goal
        # Values:
        #   undefined - user is not here to receive tips, but will generally regift them
        #   null - user has no funding goal
        #   3.00 - user wishes to receive at least this amount
        if self.goal != 0:
            if self.goal > 0:
                goal = str(self.goal)
            else:
                goal = None
            output['goal'] = goal

        # Key: receiving
        # Values:
        #   null - user is receiving anonymously
        #   3.00 - user receives this amount in tips
        if not self.anonymous_receiving:
            receiving = str(self.get_dollars_receiving())
        else:
            receiving = None
        output['receiving'] = receiving

        # Key: giving
        # Values:
        #   null - user is giving anonymously
        #   3.00 - user gives this amount in tips
        if not self.anonymous_giving:
            giving = str(self.get_dollars_giving())
        else:
            giving = None
        output['giving'] = giving

        # Key: my_tip
        # Values:
        #   undefined - user is not authenticated
        #   "self" - user == participant
        #   null - user has never tipped this person
        #   0.00 - user used to tip this person but now doesn't
        #   3.00 - user tips this person this amount
        if inquirer:
            if inquirer.username == self.username:
                my_tip = 'self'
            else:
                my_tip = inquirer.get_tip_to(self.username)
            output['my_tip'] = str(my_tip)

        # Key: elsewhere
        accounts = self.get_accounts_elsewhere()
        elsewhere = output['elsewhere'] = {}
        for platform, account in accounts.items():
            fields = ['id', 'user_id', 'user_name']
            elsewhere[platform] = {k: getattr(account, k, None) for k in fields}

        # Key: bitcoin
        if self.bitcoin_address is not None:
            output['bitcoin'] = 'https://blockchain.info/address/%s' % self.bitcoin_address

        return output


class NeedConfirmation(Exception):
    """Represent the case where we need user confirmation during a merge.

    This is used in the workflow for merging one participant into another.

    """

    def __init__(self, a, b, c):
        self.other_is_a_real_participant = a
        self.this_is_others_last_account_elsewhere = b
        self.we_already_have_that_kind_of_account = c
        self._all = (a, b, c)

    def __repr__(self):
        return "<NeedConfirmation: %r %r %r>" % self._all
    __str__ = __repr__

    def __eq__(self, other):
        return self._all == other._all

    def __ne__(self, other):
        return not self.__eq__(other)

    def __nonzero__(self):
        # bool(need_confirmation)
        A, B, C = self._all
        return A or C

class LastElsewhere(Exception): pass

class NonexistingElsewhere(Exception): pass

class TeamCantBeOnlyAuth(Exception): pass
