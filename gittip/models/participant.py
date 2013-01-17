import datetime
from decimal import Decimal

import pytz
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import relationship
from sqlalchemy.schema import Column, CheckConstraint, UniqueConstraint
from sqlalchemy.types import Text, TIMESTAMP, Boolean, Numeric
from aspen import Response

import gittip
from gittip.orm import db
from gittip.models import Elsewhere
# This is loaded for now to maintain functionality until the class is fully
# migrated over to doing everything using SQLAlchemy
from gittip.participant import Participant as ParticipantClass

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
    goal = Column(Numeric(precision=35, scale=2), default=None)
    balanced_account_uri = Column(Text)
    last_ach_result = Column(Text)
    is_suspicious = Column(Boolean)

    ### Relations ###
    accounts_elsewhere = relationship("Elsewhere", backref="participant",
                                      lazy="dynamic")
    exchanges = relationship("Exchange", backref="participant")
    # TODO: Once tippee/tipper are renamed to tippee_id/tipper_idd, we can go
    # ahead and drop the foreign_keys & rename backrefs to tipper/tippee
    tipper_in = relationship("Tip", backref="tipper_participant",
                             foreign_keys="Tip.tipper", lazy="dynamic")
    tippee_in = relationship("Tip", backref="tippee_participant",
                             foreign_keys="Tip.tippee", lazy="dynamic")
    transferer = relationship("Transfer", backref="transferer",
                             foreign_keys="Transfer.tipper")
    transferee = relationship("Transfer", backref="transferee",
                             foreign_keys="Transfer.tippee")

    # Class-specific exceptions
    class IdTooLong(Exception): pass
    class IdContainsInvalidCharacters(Exception): pass
    class IdIsRestricted(Exception): pass
    class IdAlreadyTaken(Exception): pass

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
        """Raise Response or return None.

        We want to be pretty loose with usernames. Unicode is allowed--XXX
        aspen bug :(. So are spaces.Control characters aren't. We also limit to
        32 characters in length.

        """
        for i, c in enumerate(desired_id):
            if i == 32:
                raise self.IdTooLong  # Request Entity Too Large (more or less)
            elif ord(c) < 128 and c not in ASCII_ALLOWED_IN_PARTICIPANT_ID:
                raise self.IdContainsInvalidCharacters  # Yeah, no.
            elif c not in ASCII_ALLOWED_IN_PARTICIPANT_ID:
                raise self.IdContainsInvalidCharacters  # XXX Burned by an Aspen bug. :`-(
                                                        # https://github.com/zetaweb/aspen/issues/102

        if desired_id in gittip.RESTRICTED_IDS:
            raise self.IdIsRestricted

        if desired_id != self.id:
            # Will raise sqlalchemy.exc.IntegrityError if the desired_id is taken.
            try:
                self.id = desired_id
                db.session.add(self)
                db.session.commit()
            except IntegrityError as e:
                db.session.rollback()
                raise self.IdAlreadyTaken

    def get_accounts_elsewhere(self):
        github_account = twitter_account = None
        for account in self.accounts_elsewhere.all():
            if account.platform == "github":
                github_account = account
            elif account.platform == "twitter":
                twitter_account = account
        return (github_account, twitter_account)

    def get_giving_for_profile(self):
        return ParticipantClass(self.id).get_giving_for_profile()

    def get_tip_to(self, tippee):
        tip = self.tipper_in.filter_by(tippee=tippee).first()

        if tip:
            amount = tip.amount
        else:
            amount = Decimal('0.0')

        return amount

    @property
    def dollars_giving(self):
        return sum(tip.amount for tip in self.tipper_in)

    @property
    def dollars_receiving(self):
        return sum(tip.amount for tip in self.tippee_in)

    def get_number_of_backers(self):
        return ParticipantClass(self.id).get_number_of_backers()

    def get_chart_of_receiving(self):
        # TODO: Move the query in to this class.
        return ParticipantClass(self.id).get_chart_of_receiving()

    def get_giving_for_profile(self, db=None):
        return ParticipantClass(self.id).get_giving_for_profile(db)

    def get_tips_and_total(self, for_payday=False, db=None):
        return ParticipantClass(self.id).get_tips_and_total(for_payday, db)

    def take_over(self, account_elsewhere, have_confirmation=False):
        ParticipantClass(self.id).take_over(account_elsewhere,
                                            have_confirmation)