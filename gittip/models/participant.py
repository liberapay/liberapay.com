from __future__ import unicode_literals

import datetime
import os
from decimal import Decimal

import pytz
from aspen.utils import typecheck
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import relationship, exc
from sqlalchemy.schema import Column, CheckConstraint, UniqueConstraint, Sequence
from sqlalchemy.types import Text, TIMESTAMP, Boolean, Numeric, BigInteger, Enum

import gittip
from gittip.models.tip import Tip
from gittip.orm import db
# This is loaded for now to maintain functionality until the class is fully
# migrated over to doing everything using SQLAlchemy
from gittip.participant import Participant as OldParticipant

ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                ".,-_:@ ")
NANSWERS_THRESHOLD = 0  # configured in wireup.py

class Participant(db.Model):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("session_token",
                         name="participants_session_token_key"),
    )

    id = Column(BigInteger, Sequence('participants_id_seq'), nullable=False, unique=True)
    username = Column(Text, nullable=False, primary_key=True)
    username_lower = Column(Text, nullable=False, unique=True)
    statement = Column(Text, default="", nullable=False)
    stripe_customer_id = Column(Text)
    last_bill_result = Column(Text)
    session_token = Column(Text)
    session_expires = Column(TIMESTAMP(timezone=True), default="now()")
    ctime = Column(TIMESTAMP(timezone=True), nullable=False, default="now()")
    claimed_time = Column(TIMESTAMP(timezone=True))
    is_admin = Column(Boolean, nullable=False, default=False)
    balance = Column(Numeric(precision=35, scale=2),
                     CheckConstraint("balance >= 0", name="min_balance"),
                     default=0.0, nullable=False)
    pending = Column(Numeric(precision=35, scale=2), default=None)
    anonymous = Column(Boolean, default=False, nullable=False)
    goal = Column(Numeric(precision=35, scale=2), default=None)
    balanced_account_uri = Column(Text)
    last_ach_result = Column(Text)
    api_key = Column(Text)
    is_suspicious = Column(Boolean)
    number = Column(Enum('singular', 'plural', nullable=False))

    ### Relations ###
    accounts_elsewhere = relationship( "Elsewhere"
                                     , backref="participant_orm"
                                     , lazy="dynamic"
                                      )
    exchanges = relationship("Exchange", backref="participant_orm")

    # TODO: Once tippee/tipper are renamed to tippee_id/tipper_idd, we can go
    # ahead and drop the foreign_keys & rename backrefs to tipper/tippee

    _tips_giving = relationship( "Tip"
                               , backref="tipper_participant"
                               , foreign_keys="Tip.tipper"
                               , lazy="dynamic"
                                )
    _tips_receiving = relationship( "Tip"
                                  , backref="tippee_participant"
                                  , foreign_keys="Tip.tippee"
                                  , lazy="dynamic"
                                   )

    transferer = relationship( "Transfer"
                             , backref="transferer"
                             , foreign_keys="Transfer.tipper"
                              )
    transferee = relationship( "Transfer"
                             , backref="transferee"
                             , foreign_keys="Transfer.tippee"
                              )

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
    def IS_SINGULAR(self):
        return self.number == 'singular'

    @property
    def IS_PLURAL(self):
        return self.number == 'plural'

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

    def change_username(self, desired_username):
        """Raise self.ProblemChangingUsername, or return None.

        We want to be pretty loose with usernames. Unicode is allowed--XXX
        aspen bug :(. So are spaces. Control characters aren't. We also limit
        to 32 characters in length.

        """
        for i, c in enumerate(desired_username):
            if i == 32:
                raise self.UsernameTooLong  # Request Entity Too Large (more or less)
            elif ord(c) < 128 and c not in ASCII_ALLOWED_IN_USERNAME:
                raise self.UsernameContainsInvalidCharacters  # Yeah, no.
            elif c not in ASCII_ALLOWED_IN_USERNAME:

                # XXX Burned by an Aspen bug. :`-(
                # https://github.com/gittip/aspen/issues/102

                raise self.UsernameContainsInvalidCharacters

        lowercased = desired_username.lower()

        if lowercased in gittip.RESTRICTED_USERNAMES:
            raise self.UsernameIsRestricted

        if desired_username != self.username:
            try:
                self.username = desired_username
                self.username_lower = lowercased
                db.session.add(self)
                db.session.commit()
                # Will raise sqlalchemy.exc.IntegrityError if the
                # desired_username is taken.
            except IntegrityError:
                db.session.rollback()
                raise self.UsernameAlreadyTaken

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

                # For Twitter, we don't have good control over size. We don't
                # want the original, cause that can be huge. The next option is
                # 73px(?!).
                src = src.replace('_normal.', '_bigger.')

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
        return list(gittip.db.fetchall("""

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
        rec = gittip.db.fetchone("""

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
        rec = gittip.db.fetchone( "SELECT take FROM current_memberships "
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
        gittip.db.execute("""

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
        return list(gittip.db.fetchall("""

            SELECT member AS username, take, ctime, mtime
              FROM current_memberships
             WHERE team=%s
          ORDER BY ctime DESC

        """, (self.username,)))

    def get_teams_membership(self):
        assert self.IS_PLURAL
        TAKE = "SELECT sum(take) FROM current_memberships WHERE team=%s"
        total_take = gittip.db.fetchone(TAKE, (self.username,))['sum']
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


    # TODO: Move these queries into this class.

    def set_tip_to(self, tippee, amount):
        return OldParticipant(self.username).set_tip_to(tippee, amount)

    def insert_into_communities(self, is_member, name, slug):
        return OldParticipant(self.username).insert_into_communities( is_member
                                                                    , name
                                                                    , slug
                                                                     )

    def get_dollars_giving(self):
        return OldParticipant(self.username).get_dollars_giving()

    def get_tip_distribution(self):
        return OldParticipant(self.username).get_tip_distribution()

    def get_giving_for_profile(self, db=None):
        return OldParticipant(self.username).get_giving_for_profile(db)

    def get_tips_and_total(self, for_payday=False, db=None):
        return OldParticipant(self.username).get_tips_and_total(for_payday, db)

    def take_over(self, account_elsewhere, have_confirmation=False):
        OldParticipant(self.username).take_over(account_elsewhere,
                                                have_confirmation)

    def recreate_api_key(self):
        return OldParticipant(self.username).recreate_api_key()
