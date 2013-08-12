"""Defines a Participant class.
"""
from __future__ import unicode_literals

import datetime
import os
import random
import uuid
from decimal import Decimal

import gittip
import pytz
from aspen.utils import typecheck
from psycopg2 import IntegrityError


ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                ".,-_:@ ")
NANSWERS_THRESHOLD = 0  # configured in wireup.py


class NoParticipantId(Exception):
    """Represent a bug where we treat an anonymous user as a participant.
    """


class NeedConfirmation(Exception):
    """We need confirmation before we'll proceed.
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

def gen_random_usernames():
    """Yield up to 100 random usernames.
    """
    seatbelt = 0
    while 1:
        yield hex(int(random.random() * 16**12))[2:].zfill(12).decode('ASCII')
        seatbelt += 1
        if seatbelt > 100:
            raise StopIteration


def reserve_a_random_username(txn):
    """Reserve a random username.

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


class Participant(object):
    """Represent a Gittip participant.
    """

    ################################################################
    ############### BEGIN COPY/PASTE OF ORM VERSION
    ################################################################


    @classmethod
    def from_username(cls, username):
        # Note that User.from_username overrides this. It authenticates people!
        try:
            return cls.query.filter_by(username_lower=username.lower()).one()
        except exc.NoResultFound:
            return None

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return self.id != other.id

    # Class-specific exceptions
    class ProblemChangingUsername(Exception): pass
    class UsernameTooLong(ProblemChangingUsername): pass
    class UsernameContainsInvalidCharacters(ProblemChangingUsername): pass
    class UsernameIsRestricted(ProblemChangingUsername): pass
    class UsernameAlreadyTaken(ProblemChangingUsername): pass

    class UnknownPlatform(Exception): pass
    class TooGreedy(Exception): pass
    class MemberLimitReached(Exception): pass

    @property
    def tips_giving(self):
        return self._tips_giving.distinct("tips.tippee")\
                                .order_by("tips.tippee, tips.mtime DESC")

    @property
    def tips_receiving(self):
        return self._tips_receiving.distinct("tips.tipper")\
                                   .order_by("tips.tipper, tips.mtime DESC")

    @property
    def accepts_tips(self):
        return (self.goal is None) or (self.goal >= 0)

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

    def resolve_unclaimed(self):
        if self.accounts_elsewhere:
            return self.accounts_elsewhere[0].resolve_unclaimed()
        else:
            return None

    def set_as_claimed(self, claimed_at=None):
        if claimed_at is None:
            claimed_at = datetime.datetime.now(pytz.utc)
        self.claimed_time = claimed_at
        db.session.add(self)
        db.session.commit()

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

    def get_tip_to(self, tippee):
        tip = self.tips_giving.filter_by(tippee=tippee).first()

        if tip:
            amount = tip.amount
        else:
            amount = Decimal('0.00')

        return amount

    def get_dollars_receiving(self):
        return sum(tip.amount for tip in self.valid_tips_receiving) + Decimal('0.00')

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

    def get_teams(self):
        """Return a list of teams this user is a member of.
        """
        return list(gittip.db.all("""

            SELECT team AS name
                 , ( SELECT count(*)
                       FROM current_memberships
                      WHERE team=x.team
                    ) AS nmembers
              FROM current_memberships x
             WHERE member=%s;

        """, (self.username,)))


    # Participant as Team
    # ===================

    def show_as_team(self, user):
        """Return a boolean, whether to show this participant as a team.
        """
        if not self.IS_PLURAL:
            return False
        if user.ADMIN:
            return True
        if not self.get_members():
            if self != user:
                return False
        return True

    def add_member(self, member):
        """Add a member to this team.
        """
        assert self.IS_PLURAL
        if len(self.get_members()) == 149:
            raise self.MemberLimitReached
        self.__set_take_for(member, Decimal('0.01'), self)

    def remove_member(self, member):
        """Remove a member from this team.
        """
        assert self.IS_PLURAL
        self.__set_take_for(member, Decimal('0.00'), self)

    def member_of(self, team):
        """Given a Participant object, return a boolean.
        """
        assert team.IS_PLURAL
        for member in team.get_members():
            if member['username'] == self.username:
                return True
        return False

    def get_take_last_week_for(self, member):
        """What did the user actually take most recently? Used in throttling.
        """
        assert self.IS_PLURAL
        membername = member.username if hasattr(member, 'username') \
                                                        else member['username']
        rec = gittip.db.one_or_zero("""

            SELECT amount
              FROM transfers
             WHERE tipper=%s AND tippee=%s
               AND timestamp >
                (SELECT ts_start FROM paydays ORDER BY ts_start DESC LIMIT 1)
          ORDER BY timestamp DESC LIMIT 1

        """, (self.username, membername))

        if rec is None:
            return Decimal('0.00')
        else:
            return rec['amount']

    def get_take_for(self, member):
        """Return a Decimal representation of the take for this member, or 0.
        """
        assert self.IS_PLURAL
        rec = gittip.db.one_or_zero( "SELECT take FROM current_memberships "
                                     "WHERE member=%s AND team=%s"
                                   , (member.username, self.username)
                                    )
        if rec is None:
            return Decimal('0.00')
        else:
            return rec['take']

    def compute_max_this_week(self, last_week):
        """2x last week's take, but at least a dollar.
        """
        return max(last_week * Decimal('2'), Decimal('1.00'))

    def set_take_for(self, member, take, recorder):
        """Sets member's take from the team pool.
        """
        assert self.IS_PLURAL
        from gittip.models.user import User  # lazy to avoid circular import
        typecheck( member, Participant
                 , take, Decimal
                 , recorder, (Participant, User)
                  )

        last_week = self.get_take_last_week_for(member)
        max_this_week = self.compute_max_this_week(last_week)
        if take > max_this_week:
            take = max_this_week

        self.__set_take_for(member, take, recorder)
        return take

    def __set_take_for(self, member, take, recorder):
        assert self.IS_PLURAL
        # XXX Factored out for testing purposes only! :O Use .set_take_for.
        gittip.db.run("""

            INSERT INTO memberships (ctime, member, team, take, recorder)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM memberships
                                   WHERE member=%s
                                     AND team=%s
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , %s
                    , %s
                    , %s
                    , %s
                     )

        """, (member.username, self.username, member.username, self.username, \
                                                      take, recorder.username))

    def get_members(self):
        assert self.IS_PLURAL
        return list(gittip.db.all("""

            SELECT member AS username, take, ctime, mtime
              FROM current_memberships
             WHERE team=%s
          ORDER BY ctime DESC

        """, (self.username,)))

    def get_teams_membership(self):
        assert self.IS_PLURAL
        TAKE = "SELECT sum(take) FROM current_memberships WHERE team=%s"
        total_take = gittip.db.one_or_zero(TAKE, (self.username,))['sum']
        total_take = 0 if total_take is None else total_take
        team_take = max(self.get_dollars_receiving() - total_take, 0)
        membership = { "ctime": None
                     , "mtime": None
                     , "username": self.username
                     , "take": team_take
                      }
        return membership

    def get_memberships(self, current_user):
        assert self.IS_PLURAL
        members = self.get_members()
        members.append(self.get_teams_membership())
        budget = balance = self.get_dollars_receiving()
        for member in members:
            member['removal_allowed'] = current_user == self
            member['editing_allowed'] = False
            if member['username'] == current_user.username:
                member['is_current_user'] = True
                if member['ctime'] is not None:
                    # current user, but not the team itself
                    member['editing_allowed']= True
            take = member['take']
            member['take'] = take
            member['last_week'] = last_week = \
                                            self.get_take_last_week_for(member)
            member['max_this_week'] = self.compute_max_this_week(last_week)
            amount = min(take, balance)
            balance -= amount
            member['balance'] = balance
            member['percentage'] = (amount / budget) if budget > 0 else 0
        return members




    ################################################################
    ############### END COPY/PASTE OF ORM VERSION
    ################################################################

    class NoSelfTipping(Exception): pass
    class BadAmount(Exception): pass

    # Username exceptions
    class ProblemChangingUsername(Exception): pass
    class UsernameTooLong(ProblemChangingUsername): pass
    class UsernameContainsInvalidCharacters(ProblemChangingUsername): pass
    class UsernameIsRestricted(ProblemChangingUsername): pass
    class UsernameAlreadyTaken(ProblemChangingUsername): pass


    def __init__(self, username):
        typecheck(username, (unicode, None))
        self.username = username


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



    # Accounts Elsewhere
    # ==================

    def take_over(self, account_elsewhere, have_confirmation=False):
        """Given two unicodes, raise WontProceed or return None.

        This method associates an account on another platform (GitHub, Twitter,
        etc.) with the Gittip participant represented by self. Every account
        elsewhere has an associated Gittip participant account, even if its
        only a stub participant (it allows us to track pledges to that account
        should they ever decide to join Gittip).

        In certain circumstances, we want to present the user with a
        confirmation before proceeding to reconnect the account elsewhere to
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
        platform = account_elsewhere.platform
        user_id = account_elsewhere.user_id

        typecheck(platform, unicode, user_id, unicode, have_confirmation, bool)

        CONSOLIDATE_TIPS_RECEIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), tipper, %s AS tippee, sum(amount)
                   FROM (   SELECT DISTINCT ON (tipper, tippee)
                                   ctime, tipper, tippee, amount
                              FROM tips
                          ORDER BY tipper, tippee, mtime DESC
                         ) AS unique_tips
                  WHERE (tippee=%s OR tippee=%s)
                AND NOT (tipper=%s AND tippee=%s)
                AND NOT (tipper=%s)
               GROUP BY tipper

        """

        CONSOLIDATE_TIPS_GIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), %s AS tipper, tippee, sum(amount)
                   FROM (   SELECT DISTINCT ON (tipper, tippee)
                                   ctime, tipper, tippee, amount
                              FROM tips
                          ORDER BY tipper, tippee, mtime DESC
                         ) AS unique_tips
                  WHERE (tipper=%s OR tipper=%s)
                AND NOT (tipper=%s AND tippee=%s)
                AND NOT (tippee=%s)
               GROUP BY tippee

        """

        ZERO_OUT_OLD_TIPS_RECEIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT DISTINCT ON (tipper) ctime, tipper, tippee, 0 AS amount
                   FROM tips
                  WHERE tippee=%s

        """

        ZERO_OUT_OLD_TIPS_GIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT DISTINCT ON (tippee) ctime, tipper, tippee, 0 AS amount
                   FROM tips
                  WHERE tipper=%s

        """

        with gittip.db.get_transaction() as txn:

            # Load the existing connection.
            # =============================
            # Every account elsewhere has at least a stub participant account
            # on Gittip.

            txn.execute("""

                SELECT participant
                     , claimed_time IS NULL AS is_stub
                  FROM elsewhere
                  JOIN participants ON participant=participants.username
                 WHERE elsewhere.platform=%s AND elsewhere.user_id=%s

            """, (platform, user_id))
            rec = txn.fetchone()
            assert rec is not None          # sanity check

            other_username = rec['participant']


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
            other_is_a_real_participant = not rec['is_stub']

            # this_is_others_last_account_elsewhere
            txn.execute( "SELECT count(*) AS nelsewhere FROM elsewhere "
                         "WHERE participant=%s"
                       , (other_username,)
                        )
            nelsewhere = txn.fetchone()['nelsewhere']
            assert nelsewhere > 0           # sanity check
            this_is_others_last_account_elsewhere = nelsewhere == 1

            # we_already_have_that_kind_of_account
            txn.execute( "SELECT count(*) AS nparticipants FROM elsewhere "
                         "WHERE participant=%s AND platform=%s"
                       , (self.username, platform)
                        )
            nparticipants = txn.fetchone()['nparticipants']
            assert nparticipants in (0, 1)  # sanity check
            we_already_have_that_kind_of_account = nparticipants == 1

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
                new_stub_username = reserve_a_random_username(txn)
                txn.execute( "UPDATE elsewhere SET participant=%s "
                             "WHERE platform=%s AND participant=%s"
                           , (new_stub_username, platform, self.username)
                            )


            # Do the deal.
            # ============
            # If other_is_not_a_stub, then other will have the account
            # elsewhere taken away from them with this call. If there are other
            # browsing sessions open from that account, they will stay open
            # until they expire (XXX Is that okay?)

            txn.execute( "UPDATE elsewhere SET participant=%s "
                         "WHERE platform=%s AND user_id=%s"
                       , (self.username, platform, user_id)
                        )


            # Fold the old participant into the new as appropriate.
            # =====================================================
            # We want to do this whether or not other is a stub participant.

            if this_is_others_last_account_elsewhere:

                # Take over tips.
                # ===============

                x, y = self.username, other_username
                txn.execute(CONSOLIDATE_TIPS_RECEIVING, (x, x,y, x,y, x))
                txn.execute(CONSOLIDATE_TIPS_GIVING, (x, x,y, x,y, x))
                txn.execute(ZERO_OUT_OLD_TIPS_RECEIVING, (other_username,))
                txn.execute(ZERO_OUT_OLD_TIPS_GIVING, (other_username,))


                # Archive the old participant.
                # ============================
                # We always give them a new, random username. We sign out
                # the old participant.

                for archive_username in gen_random_usernames():
                    try:
                        txn.execute("""

                            UPDATE participants
                               SET username=%s
                                 , username_lower=%s
                                 , session_token=NULL
                                 , session_expires=now()
                             WHERE username=%s
                         RETURNING username

                        """, ( archive_username
                             , archive_username.lower()
                             , other_username)
                              )
                        rec = txn.fetchone()
                    except IntegrityError:
                        continue  # archive_username is already taken;
                                  # extremely unlikely, but ...
                                  # XXX But can the UPDATE fail in other ways?
                    else:
                        assert rec is not None  # sanity checks
                        assert rec['username'] == archive_username
                        break


                # Record the absorption.
                # ======================
                # This is for preservation of history.

                txn.execute( "INSERT INTO absorptions "
                             "(absorbed_was, absorbed_by, archived_as) "
                             "VALUES (%s, %s, %s)"
                           , (other_username, self.username, archive_username)
                            )


            # Lastly, keep account_elsewhere in sync.
            # =======================================
            # Bandaid for
            #
            #   https://github.com/gittip/www.gittip.com/issues/421
            #
            # XXX This is why we're porting to SQLAlchemy:
            #
            #   https://github.com/gittip/www.gittip.com/issues/129

            account_elsewhere.participant = self.username
