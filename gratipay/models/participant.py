"""*Participant* is the name Gratipay gives to people and groups that are known
to Gratipay. We've got a ``participants`` table in the database, and a
:py:class:`Participant` class that we define here. We distinguish several kinds
of participant, based on certain properties.

 - *Stub* participants
 - *Organizations* are plural participants
 - *Teams* are plural participants with members

"""
from __future__ import print_function, unicode_literals

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN
import uuid

import aspen
from aspen.utils import typecheck, utcnow
from postgres.orm import Model
from psycopg2 import IntegrityError

import gratipay
from gratipay import NotSane
from gratipay.exceptions import (
    HasBigTips,
    UsernameIsEmpty,
    UsernameTooLong,
    UsernameContainsInvalidCharacters,
    UsernameIsRestricted,
    UsernameAlreadyTaken,
    NoSelfTipping,
    NoTippee,
    BadAmount,
    UserDoesntAcceptTips,
)

from gratipay.models import add_event
from gratipay.models._mixin_team import MixinTeam
from gratipay.models.account_elsewhere import AccountElsewhere
from gratipay.utils.username import safely_reserve_a_username
from gratipay import billing
from gratipay.utils import is_card_expiring


ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                ".,-_:@ ")
# We use | in Sentry logging, so don't make that allowable. :-)

NANSWERS_THRESHOLD = 0  # configured in wireup.py

NOTIFIED_ABOUT_EXPIRATION = b'notifiedAboutExpiration'

class Participant(Model, MixinTeam):
    """Represent a Gratipay participant.
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
        if participant and participant.session_expires < utcnow():
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

    def update_session(self, new_token, expires):
        """Set ``session_token`` and ``session_expires``.

        :database: One UPDATE, one row

        """
        self.db.run("""
            UPDATE participants
               SET session_token=%s
                 , session_expires=%s
             WHERE id=%s
               AND is_suspicious IS NOT true
        """, (new_token, expires, self.id))
        self.set_attributes(session_token=new_token, session_expires=expires)

    def set_session_expires(self, expires):
        """Set ``session_expires`` to the given datetime.

        :database: One UPDATE, one row

        """
        self.db.run( "UPDATE participants SET session_expires=%s "
                     "WHERE id=%s AND is_suspicious IS NOT true"
                   , (expires, self.id,)
                    )
        self.set_attributes(session_expires=expires)


    # Suspiciousness
    # ==============

    @property
    def is_whitelisted(self):
        return self.is_suspicious is False


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
            """, (self.username, gratipay.MAX_TIP_SINGULAR))
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


    # Pricing
    # =======

    @property
    def usage(self):
        return max(self.giving + self.pledging, self.receiving)

    @property
    def suggested_payment(self):
        usage = self.usage
        if usage >= 500:
            percentage = Decimal('0.02')
        elif usage >= 20:
            percentage = Decimal('0.05')
        else:
            percentage = Decimal('0.10')

        suggestion = usage * percentage
        if suggestion == 0:
            rounded = suggestion
        elif suggestion < 0.25:
            rounded = Decimal('0.25')
        elif suggestion < 0.50:
            rounded = Decimal('0.50')
        elif suggestion < 1:
            rounded = Decimal('1.00')
        else:
            rounded = suggestion.quantize(Decimal('0'), ROUND_HALF_EVEN)

        return rounded


    # API Key
    # =======

    def recreate_api_key(self):
        api_key = self._generate_api_key()
        SQL = "UPDATE participants SET api_key=%s WHERE username=%s RETURNING api_key"
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(action='set', id=self.id, values=dict(api_key=api_key)))
            api_key = c.one(SQL, (api_key, self.username))
        self.set_attributes(api_key=api_key)
        return api_key

    def _generate_api_key(self):
        return str(uuid.uuid4())


    # Claiming
    # ========
    # An unclaimed Participant is a stub that's created when someone pledges to
    # give to an AccountElsewhere that's not been connected on Gratipay yet.

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


    # Closing
    # =======

    class UnknownDisbursementStrategy(Exception): pass

    def close(self, disbursement_strategy):
        """Close the participant's account.
        """
        with self.db.get_cursor() as cursor:
            if disbursement_strategy == None:
                pass  # No balance, supposedly. final_check will make sure.
            elif disbursement_strategy == 'bank':
                self.withdraw_balance_to_bank_account(cursor)
            elif disbursement_strategy == 'downstream':
                # This in particular needs to come before clear_tips_giving.
                self.distribute_balance_as_final_gift(cursor)
            else:
                raise self.UnknownDisbursementStrategy

            self.clear_tips_giving(cursor)
            self.clear_tips_receiving(cursor)
            self.clear_personal_information(cursor)
            self.final_check(cursor)
            self.update_is_closed(True, cursor)


    def withdraw_balance_to_bank_account(self, cursor):
        from gratipay.billing.exchanges import ach_credit
        ach_credit( self.db
                  , self
                  , Decimal('0.00') # don't withhold anything
                  , Decimal('0.00') # send it all
                   )


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
            rate = tip.amount / claimed_total
            pro_rated = (self.balance * rate).quantize(Decimal('0.01'), ROUND_DOWN)
            if pro_rated == 0:
                continue
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
            cursor.run( "INSERT INTO transfers (tipper, tippee, amount, context) "
                        "VALUES (%s, %s, %s, 'final-gift')"
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
            self.set_tip_to(tippee, '0.00', update_self=False, cursor=cursor)

    def clear_tips_receiving(self, cursor):
        """Zero out tips to a given user.
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
            tipper.set_tip_to(self, '0.00', update_tippee=False, cursor=cursor)


    def clear_takes(self, cursor):
        """Leave all teams by zeroing all takes.
        """
        for team, nmembers in self.get_teams():
            t = Participant.from_username(team)
            t.set_take_for(self, Decimal(0), self, cursor)


    def clear_personal_information(self, cursor):
        """Clear personal information such as statement and goal.
        """
        if self.IS_PLURAL:
            self.remove_all_members(cursor)
        self.clear_takes(cursor)
        r = cursor.one("""

            INSERT INTO community_members (slug, participant, ctime, name, is_member) (
                SELECT slug, participant, ctime, name, false
                  FROM community_members
                 WHERE participant=%(participant_id)s
                   AND is_member IS true
            );

            UPDATE participants
               SET statement=''
                 , goal=NULL
                 , anonymous_giving=False
                 , anonymous_receiving=False
                 , number='singular'
                 , avatar_url=NULL
                 , email=NULL
                 , claimed_time=NULL
                 , session_token=NULL
                 , session_expires=now()
                 , giving=0
                 , pledging=0
                 , receiving=0
                 , npatrons=0
             WHERE username=%(username)s
         RETURNING *;

        """, dict(username=self.username, participant_id=self.id))
        self.set_attributes(**r._asdict())


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
        participant_id = self.id
        self.db.run("""

            INSERT INTO community_members
                        (ctime, name, slug, participant, is_member)
                 VALUES ( COALESCE (( SELECT ctime
                                        FROM community_members
                                       WHERE participant=%(participant_id)s
                                         AND slug=%(slug)s
                                       LIMIT 1
                                      ), CURRENT_TIMESTAMP)
                        , %(name)s, %(slug)s, %(participant_id)s, %(is_member)s
                         )
              RETURNING ( SELECT count(*) = 0
                            FROM community_members
                           WHERE participant=%(participant_id)s
                         )
                     AS first_time_community

        """, locals())


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

        if lowercased in gratipay.RESTRICTED_USERNAMES:
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
            r = c.one("UPDATE participants SET email = ROW(%s, %s) WHERE username=%s RETURNING email"
                     , (email, confirmed, self.username)
                      )
            self.set_attributes(email=r)

    def update_goal(self, goal):
        typecheck(goal, (Decimal, None))
        with self.db.get_cursor() as c:
            tmp = goal if goal is None else unicode(goal)
            add_event(c, 'participant', dict(id=self.id, action='set', values=dict(goal=tmp)))
            c.one( "UPDATE participants SET goal=%s WHERE username=%s RETURNING id"
                 , (goal, self.username)
                  )
            self.set_attributes(goal=goal)
            if not self.accepts_tips:
                self.clear_tips_receiving(c)
                self.update_receiving(c)

    def update_is_closed(self, is_closed, cursor=None):
        with self.db.get_cursor(cursor) as cursor:
            cursor.run( "UPDATE participants SET is_closed=%(is_closed)s "
                        "WHERE username=%(username)s"
                      , dict(username=self.username, is_closed=is_closed)
                       )
            add_event( cursor
                     , 'participant'
                     , dict(id=self.id, action='set', values=dict(is_closed=is_closed))
                      )
            self.set_attributes(is_closed=is_closed)

    def update_giving(self, cursor=None):
        giving = (cursor or self.db).one("""
            UPDATE participants p
               SET giving = COALESCE((
                       SELECT sum(amount)
                         FROM current_tips
                         JOIN participants p2 ON p2.username = tippee
                        WHERE tipper = p.username
                          AND p2.claimed_time IS NOT NULL
                          AND p2.is_suspicious IS NOT true
                     GROUP BY tipper
                   ), 0)
             WHERE p.username = %s
         RETURNING giving
        """, (self.username,))
        self.set_attributes(giving=giving)

    def update_pledging(self, cursor=None):
        pledging = (cursor or self.db).one("""
            UPDATE participants p
               SET pledging = COALESCE((
                       SELECT sum(amount)
                         FROM current_tips
                         JOIN participants p2 ON p2.username = tippee
                         JOIN elsewhere ON elsewhere.participant = tippee
                        WHERE tipper = p.username
                          AND p2.claimed_time IS NULL
                          AND elsewhere.is_locked = false
                          AND p2.is_suspicious IS NOT true
                     GROUP BY tipper
                   ), 0)
             WHERE p.username = %s
         RETURNING pledging
        """, (self.username,))
        self.set_attributes(pledging=pledging)

    def update_receiving(self, cursor=None):
        if self.IS_PLURAL:
            old_takes = self.compute_actual_takes(cursor=cursor)
        r = (cursor or self.db).one("""
            WITH our_tips AS (
                     SELECT amount
                       FROM current_tips
                       JOIN participants p2 ON p2.username = tipper
                      WHERE tippee = %(username)s
                        AND p2.is_suspicious IS NOT true
                        AND p2.last_bill_result = ''
                        AND amount > 0
                 )
            UPDATE participants p
               SET receiving = (COALESCE((
                       SELECT sum(amount)
                         FROM our_tips
                   ), 0) + taking)
                 , npatrons = COALESCE((SELECT count(*) FROM our_tips), 0)
             WHERE p.username = %(username)s
         RETURNING receiving, npatrons
        """, dict(username=self.username))
        self.set_attributes(receiving=r.receiving, npatrons=r.npatrons)
        if self.IS_PLURAL:
            new_takes = self.compute_actual_takes(cursor=cursor)
            self.update_taking(old_takes, new_takes, cursor=cursor)

    def update_is_free_rider(self, is_free_rider, cursor=None):
        with self.db.get_cursor(cursor) as cursor:
            cursor.run( "UPDATE participants SET is_free_rider=%(is_free_rider)s "
                        "WHERE username=%(username)s"
                      , dict(username=self.username, is_free_rider=is_free_rider)
                       )
            add_event( cursor
                     , 'participant'
                     , dict(id=self.id, action='set', values=dict(is_free_rider=is_free_rider))
                      )
            self.set_attributes(is_free_rider=is_free_rider)


    def set_tip_to(self, tippee, amount, update_self=True, update_tippee=True, cursor=None):
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
        assert self.is_claimed  # sanity check

        if not isinstance(tippee, Participant):
            tippee, u = Participant.from_username(tippee), tippee
            if not tippee:
                raise NoTippee(u)

        if self.username == tippee.username:
            raise NoSelfTipping

        amount = Decimal(amount)  # May raise InvalidOperation
        max_tip = gratipay.MAX_TIP_PLURAL if tippee.IS_PLURAL else gratipay.MAX_TIP_SINGULAR
        if (amount < gratipay.MIN_TIP) or (amount > max_tip):
            raise BadAmount

        if not tippee.accepts_tips and amount != 0:
            raise UserDoesntAcceptTips

        # Insert tip
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

        if update_self:
            # Update giving/pledging amount of tipper
            if tippee.is_claimed:
                self.update_giving(cursor)
            else:
                self.update_pledging(cursor)
        if update_tippee:
            # Update receiving amount of tippee
            tippee.update_receiving(cursor)
        if tippee.username == 'Gratipay':
            # Update whether the tipper is using Gratipay for free
            self.update_is_free_rider(None if amount == 0 else False, cursor)

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
        # themselves opted into Gratipay. For the tipper's profile page we want
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


    def get_current_tips(self):
        """Get the tips this participant is currently sending to others.
        """
        TIPS = """
            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , p.claimed_time
                  FROM tips t
                  JOIN participants p ON p.username = t.tippee
                 WHERE tipper = %s
                   AND p.is_suspicious IS NOT true
              ORDER BY tippee
                     , t.mtime DESC
            ) AS foo
            ORDER BY amount DESC
                   , tippee
        """
        return self.db.all(TIPS, (self.username,), back_as=dict)


    def get_og_title(self):
        out = self.username
        receiving = self.receiving
        giving = self.giving
        if (giving > receiving) and not self.anonymous_giving:
            out += " gives $%.2f/wk" % giving
        elif receiving > 0 and not self.anonymous_receiving:
            out += " receives $%.2f/wk" % receiving
        else:
            out += " is"
        return out + " on Gratipay"


    def get_age_in_seconds(self):
        out = -1
        if self.claimed_time is not None:
            now = utcnow()
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


    def get_elsewhere_logins(self, cursor):
        """Return the list of (platform, user_id) tuples that the participant
        can log in with.
        """
        return cursor.all("""
            SELECT platform, user_id
              FROM elsewhere
             WHERE participant=%s
               AND platform IN %s
               AND NOT is_team
        """, (self.username, AccountElsewhere.signin_platforms_names))


    class StillReceivingTips(Exception): pass
    class BalanceIsNotZero(Exception): pass

    def final_check(self, cursor):
        """Sanity-check that balance and tips have been dealt with.
        """
        INCOMING = "SELECT count(*) FROM current_tips WHERE tippee = %s AND amount > 0"
        if cursor.one(INCOMING, (self.username,)) > 0:
            raise self.StillReceivingTips
        if self.balance != 0:
            raise self.BalanceIsNotZero

    def archive(self, cursor):
        """Given a cursor, use it to archive ourself.

        Archiving means changing to a random username so the username they were
        using is released. We also sign them out.

        """

        self.final_check(cursor)

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
        etc.) with the given Gratipay participant. Every account elsewhere has an
        associated Gratipay participant account, even if its only a stub
        participant (it allows us to track pledges to that account should they
        ever decide to join Gratipay).

        In certain circumstances, we want to present the user with a
        confirmation before proceeding to transfer the account elsewhere to
        the new Gratipay account; NeedConfirmation is the signal to request
        confirmation. If it was the last account elsewhere connected to the old
        Gratipay account, then we absorb the old Gratipay account into the new one,
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

            SELECT ctime, tipper, tippee, amount
              FROM current_tips
             WHERE amount > 0;

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

               GROUP BY tippee

        """

        ZERO_OUT_OLD_TIPS_RECEIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM __temp_unique_tips
                 WHERE tippee=%s

        """

        ZERO_OUT_OLD_TIPS_GIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM __temp_unique_tips
                 WHERE tipper=%s

        """

        TRANSFER_BALANCE_1 = """

            UPDATE participants
               SET balance = (balance - %(balance)s)
             WHERE username=%(dead)s
         RETURNING balance;

        """

        TRANSFER_BALANCE_2 = """

            INSERT INTO transfers (tipper, tippee, amount, context)
            SELECT %(dead)s, %(live)s, %(balance)s, 'take-over'
             WHERE %(balance)s > 0;

            UPDATE participants
               SET balance = (balance + %(balance)s)
             WHERE username=%(live)s
         RETURNING balance;

        """

        new_balance = None

        with self.db.get_cursor() as cursor:

            # Load the existing connection.
            # =============================
            # Every account elsewhere has at least a stub participant account
            # on Gratipay.

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
            #       account elsewhere away from another viable Gratipay
            #       participant
            #
            #   - the other participant has no other accounts elsewhere; taking
            #       away the account elsewhere will leave the other Gratipay
            #       participant without any means of logging in, and it will be
            #       archived and its tips absorbed by us
            #
            #   - we already have an account elsewhere connected from the given
            #       platform, and it will be handed off to a new stub
            #       participant

            # other_is_a_real_participant
            other_is_a_real_participant = other.is_claimed

            # this_is_others_last_login_account
            nelsewhere = len(other.get_elsewhere_logins(cursor))
            this_is_others_last_login_account = (nelsewhere <= 1)

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
                                                , this_is_others_last_login_account
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
            # elsewhere taken away from them with this call.

            cursor.run( "UPDATE elsewhere SET participant=%s "
                        "WHERE platform=%s AND user_id=%s"
                      , (self.username, platform, user_id)
                       )


            # Fold the old participant into the new as appropriate.
            # =====================================================
            # We want to do this whether or not other is a stub participant.

            if this_is_others_last_login_account:

                other.clear_takes(cursor)

                # Take over tips.
                # ===============

                x, y = self.username, other.username
                cursor.run(CREATE_TEMP_TABLE_FOR_UNIQUE_TIPS)
                cursor.run(CONSOLIDATE_TIPS_RECEIVING, dict(live=x, dead=y))
                cursor.run(CONSOLIDATE_TIPS_GIVING, dict(live=x, dead=y))
                cursor.run(ZERO_OUT_OLD_TIPS_RECEIVING, (other.username,))
                cursor.run(ZERO_OUT_OLD_TIPS_GIVING, (other.username,))

                # Take over balance.
                # ==================

                other_balance = other.balance
                args = dict(live=x, dead=y, balance=other_balance)
                archive_balance = cursor.one(TRANSFER_BALANCE_1, args)
                other.set_attributes(balance=archive_balance)
                new_balance = cursor.one(TRANSFER_BALANCE_2, args)

                # Disconnect any remaining elsewhere account.
                # ===========================================

                cursor.run("DELETE FROM elsewhere WHERE participant=%s", (y,))

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

        if new_balance is not None:
            self.set_attributes(balance=new_balance)

        self.update_avatar()
        self.update_giving()
        self.update_pledging()
        self.update_receiving()

    def delete_elsewhere(self, platform, user_id):
        """Deletes account elsewhere unless the user would not be able
        to log in anymore.
        """
        user_id = unicode(user_id)
        with self.db.get_cursor() as c:
            accounts = self.get_elsewhere_logins(c)
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

        if not self.balanced_customer_href:
            return False

        try:
            card = billing.BalancedCard(self.balanced_customer_href)
            year, month = card['expiration_year'], card['expiration_month']
            if not (year and month):
                return False
            card_expiring = is_card_expiring(int(year), int(month))
            response.headers.cookie[NOTIFIED_ABOUT_EXPIRATION] = self.session_token
            return card_expiring
        except Exception as e:
            if request.website.env.raise_card_expiration:
                raise
            aspen.log(e)
            request.website.tell_sentry(e, request)
            return False

    def to_dict(self, details=False, inquirer=None):
        output = { 'id': self.id
                 , 'username': self.username
                 , 'avatar': self.avatar_url
                 , 'number': self.number
                 , 'on': 'gratipay'
                 }

        if not details:
            return output

        # Key: npatrons
        output['npatrons'] = self.npatrons

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
            receiving = str(self.receiving)
        else:
            receiving = None
        output['receiving'] = receiving

        # Key: giving
        # Values:
        #   null - user is giving anonymously
        #   3.00 - user gives this amount in tips
        if not self.anonymous_giving:
            giving = str(self.giving)
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
        self.this_is_others_last_login_account = b
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
