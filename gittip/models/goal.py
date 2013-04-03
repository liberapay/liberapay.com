from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import Integer, Numeric, Text, TIMESTAMP

from gittip.orm import db

class Goal(db.Model):
    __tablename__ = 'goals'

    id = Column(Integer, nullable=False, primary_key=True)
    ctime = Column(TIMESTAMP(timezone=True), nullable=False)
    mtime = Column(TIMESTAMP(timezone=True), nullable=False, default="now()")
    participant = Column(Text
                        , ForeignKey( "participants.id"
                                    , onupdate="CASCADE"
                                    , ondelete="RESTRICT"
                                     )
                        , nullable=False
                         )
    goal = Column(Numeric(precision=35, scale=2), nullable=True)

