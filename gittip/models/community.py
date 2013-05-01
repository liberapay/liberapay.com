from sqlalchemy.schema import Column
from sqlalchemy.types import Text, BigInteger

from gittip.orm import db
from gittip import db as dear_god_why

class Community(db.Model):
    __tablename__ = 'community_summary'

    name = Column(Text)
    slug = Column(Text, primary_key=True)
    nmembers = Column(BigInteger)

    def check_membership(self, user):
        return dear_god_why.fetchone("""

        SELECT * FROM current_communities WHERE slug=%s AND participant=%s

        """, (self.slug, user.username)) is not None
