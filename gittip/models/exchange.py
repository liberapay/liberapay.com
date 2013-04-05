from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import Integer, Numeric, Text, TIMESTAMP

from gittip.orm import db

class Exchange(db.Model):
    __tablename__ = 'exchanges'

    id = Column(Integer, nullable=False, primary_key=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False,
                       default="now()")
    amount = Column(Numeric(precision=35, scale=2), nullable=False)
    fee = Column(Numeric(precision=35, scale=2), nullable=False)
    participant = Column(Text, ForeignKey("participants.username",
                         onupdate="CASCADE", ondelete="RESTRICT"),
                         nullable=False)
