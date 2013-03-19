from __future__ import unicode_literals

import datetime
import os
from decimal import Decimal

import pytz
from aspen.utils import typecheck
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import relationship
from sqlalchemy.schema import Column, CheckConstraint, UniqueConstraint
from sqlalchemy.types import Text, TIMESTAMP, Boolean, Numeric
from sqlalchemy.sql.expression import desc

import gittip
from gittip.models.tip import Tip
from gittip.models.goal import Goal
from gittip.orm import db
# This is loaded for now to maintain functionality until the class is fully
# migrated over to doing everything using SQLAlchemy
from gittip.participant import Participant as OldParticipant

ASCII_ALLOWED_IN_PARTICIPANT_ID = set("0123456789"
                                      "abcdefghijklmnopqrstuvwxyz"
                                      "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                      ".,-_;:@ ")

class Participant(db.Model):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("session_token",
                         name="participants_session_token_key"),
    )

    id = Column(Text, nullable=False, primary_key=True)
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
    balanced_account_uri = Column(Text)
    last_ach_result = Column(Text)
    is_suspicious = Column(Boolean)

    ### Relations ###
    accounts_elsewhere = relationship( "Elsewhere"
                                     , backref="participant"
                                     , lazy="dynamic"
                                      )
    exchanges = relationship("Exchange", backref="participant")

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

    _goal = relationship( "Goal"
                        , backref="goal"
                        , foreign_keys="Goal.participant"
                        , lazy="dynamic"
                         )

    def __eq__(self, other):
        return self.id == other.id

    def __ne__(self, other):
        return self.id != other.id

    # Class-specific exceptions
    class ProblemChangingId(Exception): pass
    class IdTooLong(ProblemChangingId): pass
    class IdContainsInvalidCharacters(ProblemChangingId): pass
    class IdIsRestricted(ProblemChangingId): pass
    class IdAlreadyTaken(ProblemChangingId): pass

    class UnknownPlatform(Exception): pass

    @property
    def tips_giving(self):
        return self._tips_giving.distinct("tips.tippee")\
                                .order_by("tips.tippee, tips.mtime DESC")

    @property
    def tips_receiving(self):
        return self._tips_receiving.distinct("tips.tipper")\
                                   .order_by("tips.tipper, tips.mtime DESC")

    @property
    def valid_tips_receiving(self):
        return self.tips_receiving \
                   .join(Participant, Tip.tipper == Participant.id) \
                   .filter( 'participants.is_suspicious IS NOT true'
                          , Participant.last_bill_result == ''
                           )
    class goal(object):
        def __get__(self, participant, other):
            res = self.most_recent_goal(participant)
            return res.amount if res is not None else None

        def __set__(self, participant, value):
            last_goal = self.most_recent_goal(participant)
            exising_create_time = last_goal.ctime if last_goal else None
            existing_or_current_ctime = func.coalesce(  exising_create_time
                                                      , func.current_timestamp()
                                                      )
            created = db.session.query(existing_or_current_ctime).as_scalar()
            goal = Goal( ctime=created
                       , participant=participant.id
                       , amount=value
                        )
            db.session.add(goal)

        def most_recent_goal(self, participant):
            query = participant._goal.distinct("goals.participant")\
                                  .order_by(
                                        "goals.participant, goals.mtime DESC"
                                  )
            return query.first()
    goal = goal()

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

    def change_id(self, desired_id):
        """Raise self.ProblemChangingId, or return None.

        We want to be pretty loose with usernames. Unicode is allowed--XXX
        aspen bug :(. So are spaces. Control characters aren't. We also limit
        to 32 characters in length.

        """
        for i, c in enumerate(desired_id):
            if i == 32:
                raise self.IdTooLong  # Request Entity Too Large (more or less)
            elif ord(c) < 128 and c not in ASCII_ALLOWED_IN_PARTICIPANT_ID:
                raise self.IdContainsInvalidCharacters  # Yeah, no.
            elif c not in ASCII_ALLOWED_IN_PARTICIPANT_ID:

                # XXX Burned by an Aspen bug. :`-(
                # https://github.com/gittip/aspen/issues/102

                raise self.IdContainsInvalidCharacters

        if desired_id in gittip.RESTRICTED_IDS:
            raise self.IdIsRestricted

        if desired_id != self.id:
            try:
                self.id = desired_id
                db.session.add(self)
                db.session.commit()
                # Will raise sqlalchemy.exc.IntegrityError if the desired_id is
                # taken.
            except IntegrityError:
                db.session.rollback()
                raise self.IdAlreadyTaken

    def get_accounts_elsewhere(self):
        github_account = twitter_account = None
        for account in self.accounts_elsewhere.all():
            if account.platform == "github":
                github_account = account
            elif account.platform == "twitter":
                twitter_account = account
            else:
                raise self.UnknownPlatform(account.platform)
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

        github, twitter = self.get_accounts_elsewhere()
        if github is not None:
            # GitHub -> Gravatar: http://en.gravatar.com/site/implement/images/
            if 'gravatar_id' in github.user_info:
                gravatar_hash = github.user_info['gravatar_id']
                src = "https://www.gravatar.com/avatar/%s.jpg?s=%s"
                src %= (gravatar_hash, size)

        elif twitter is not None:
            # https://dev.twitter.com/docs/api/1/get/users/profile_image/%3Ascreen_name
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
        out = self.id
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


    # TODO: Move these queries into this class.

    def set_tip_to(self, tippee_id, amount):
        return OldParticipant(self.id).set_tip_to(tippee_id, amount)

    def get_dollars_giving(self):
        return OldParticipant(self.id).get_dollars_giving()

    def get_tip_distribution(self):
        return OldParticipant(self.id).get_tip_distribution()

    def get_giving_for_profile(self, db=None):
        return OldParticipant(self.id).get_giving_for_profile(db)

    def get_tips_and_total(self, for_payday=False, db=None):
        return OldParticipant(self.id).get_tips_and_total(for_payday, db)

    def take_over(self, account_elsewhere, have_confirmation=False):
        OldParticipant(self.id).take_over(account_elsewhere,
                                            have_confirmation)
