import datetime

import pytz
from sqlalchemy.schema import Column, UniqueConstraint
from sqlalchemy.types import Integer, Numeric, Text, TIMESTAMP

from gittip.orm import db

class Payday(db.Model):
    __tablename__ = 'payday'
    __table_args__ = (
        UniqueConstraint('ts_end', name='paydays_ts_end_key'),
    )

    # TODO: Move this to a different module?
    EPOCH = datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)

    id = Column(Integer, nullable=False, primary_key=True)
    ts_start = Column(TIMESTAMP(timezone=True), nullable=False,
                      default="now()")
    ts_end = Column(TIMESTAMP(timezone=True), nullable=False,
                              default=EPOCH)
    nparticipants = Column(Integer, default=0)
    ntippers = Column(Integer, default=0)
    ntips = Column(Integer, default=0)
    ntransfers = Column(Integer, default=0)
    transfer_volume = Column(Numeric(precision=35, scale=2), default=0.0)
    ncc_failing = Column(Integer, default=0)
    ncc_missing = Column(Integer, default=0)
    ncharges = Column(Integer, default=0)
    charge_volume = Column(Numeric(precision=35, scale=2), default=0.0)
    charge_fees_volume = Column(Numeric(precision=35, scale=2), default=0.0)
    nachs = Column(Integer, default=0)
    ach_volume = Column(Numeric(precision=35, scale=2), default=0.0)
    ach_fees_volume = Column(Numeric(precision=35, scale=2), default=0.0)
    nach_failing = Column(Integer, default=0)