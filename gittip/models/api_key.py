from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import Integer, Text, TIMESTAMP

from gittip.orm import db

class APIKey(db.Model):
    __tablename__ = 'api_keys'

    id = Column(Integer, nullable=False, primary_key=True)
    ctime = Column(TIMESTAMP(timezone=True), nullable=False)
    mtime = Column(TIMESTAMP(timezone=True), nullable=False, default="now()")
    participant = Column(Text
                        , ForeignKey( "participants.username"
                                    , onupdate="CASCADE"
                                    , ondelete="RESTRICT"
                                     )
                        , nullable=False
                         )
    api_key = Column(Text, nullable=True)

