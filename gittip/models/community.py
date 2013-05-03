import re

from gittip.orm import db
from gittip import db as dear_god_why
from sqlalchemy.schema import Column
from sqlalchemy.types import Text, BigInteger


name_pattern = re.compile(r'^[A-Za-z0-9,._ -]+$')


def slugize(slug):
    """Convert a string to a string for an URL.
    """
    assert name_pattern.match(slug) is not None
    slug = slug.lower()
    for c in (' ', ',', '.', '_'):
        slug = slug.replace(c, '-')
    while '--' in slug:
        slug = slug.replace('--', '-')
    slug = slug.strip('-')
    return slug


class Community(db.Model):
    __tablename__ = 'community_summary'

    name = Column(Text)
    slug = Column(Text, primary_key=True)
    nmembers = Column(BigInteger)

    def check_membership(self, user):
        return dear_god_why.fetchone("""

        SELECT * FROM current_communities WHERE slug=%s AND participant=%s

        """, (self.slug, user.username)) is not None
