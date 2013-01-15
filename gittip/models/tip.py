from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import Integer, Numeric, Text, TIMESTAMP

from gittip.orm import db

class Tip(db.Model):
    __tablename__ = 'tips'

    id = Column(Integer, nullable=False, primary_key=True)
    ctime = Column(TIMESTAMP(timezone=True), nullable=False)
    mtime = Column(TIMESTAMP(timezone=True), nullable=False, default="now()")
    tipper = Column(Text, ForeignKey("participants.id", onupdate="CASCADE",
                                     ondelete="RESTRICT"), nullable=False)
    tippee = Column(Text, ForeignKey("participants.id", onupdate="CASCADE",
                                     ondelete="RESTRICT"), nullable=False)
    amount = Column(Numeric(precision=35, scale=2), nullable=False)