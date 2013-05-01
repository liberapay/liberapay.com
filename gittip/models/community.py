from sqlalchemy.schema import Column
from sqlalchemy.types import Text, BigInteger

from gittip.orm import db

class Community(db.Model):
    __tablename__ = 'community_summary'

    name = Column(Text)
    slug = Column(Text, primary_key=True)
    nmembers = Column(BigInteger)
