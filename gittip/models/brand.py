from gittip.orm import db
from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.types import BigInteger, Text


class Brand(db.Model):
    __tablename__ = 'brands'

    id = Column(BigInteger, nullable=False, primary_key=True)
    company_id = Column( BigInteger
                       , ForeignKey( "companies.id"
                                   , onupdate="RESTRICT"
                                   , ondelete="RESTRICT"
                                    )
                       , nullable=False
                        )
    name = Column(Text, nullable=False, unique=True)
    slug = Column(Text, nullable=False, unique=True)
    url = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=False, default='')
