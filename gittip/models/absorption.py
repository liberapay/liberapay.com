from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import Integer, Text, TIMESTAMP

from gittip.orm import db

class Absorption(db.Model):
    __tablename__ = 'absorptions'

    id = Column(Integer, nullable=False, primary_key=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False,
                       default="now()")
    absorbed_was = Column(Text, nullable=False)
    absorbed_by = Column(Text, ForeignKey("participants.id",
                                          onupdate="CASCADE",
                                          ondelete="RESTRICT"), nullable=False)
    archived_as = Column(Text, ForeignKey("participants.id",
                                          onupdate="RESTRICT",
                                          ondelete="RESTRICT"), nullable=False)