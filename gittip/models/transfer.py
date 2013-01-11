from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import Integer, Numeric, Text, TIMESTAMP

from gittip.orm import Base

class Transfer(Base):
    __tablename__ = 'transfers'

    id = Column(Integer, nullable=False, primary_key=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False,
                       default="now()")
    tipper = Column(Text, ForeignKey("participants.id", onupdate="CASCADE",
                                     ondelete="RESTRICT"), nullable=False)
    tippee = Column(Text, ForeignKey("participants.id", onupdate="CASCADE",
                                     ondelete="RESTRICT"), nullable=False)
    amount = Column(Numeric(precision=35, scale=2), nullable=False)