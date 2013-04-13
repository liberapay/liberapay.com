from gittip.orm import db
from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import BigInteger, Numeric, Text, TIMESTAMP


class Identification(db.Model):
    __tablename__ = 'identifications'

    id = Column(BigInteger, nullable=False, primary_key=True)
    ctime = Column(TIMESTAMP(timezone=True), nullable=False)
    mtime = Column(TIMESTAMP(timezone=True), nullable=False, default="now()")

    individual = Column(Text, ForeignKey( "participants.username"
                                        , onupdate="CASCADE"
                                        , ondelete="RESTRICT"
                                         ), nullable=False)
    group = Column(Text, ForeignKey( "participants.username"
                                   , onupdate="CASCADE"
                                   , ondelete="RESTRICT"
                                    ), nullable=False)
    weight = Column(Numeric(precision=17, scale=16), nullable=False)
    identified_by = Column(Text, ForeignKey( "participants.username"
                                           , onupdate="CASCADE"
                                           , ondelete="RESTRICT"
                                            ), nullable=False)
