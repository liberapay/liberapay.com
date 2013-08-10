import re

import gittip
from gittip.orm import db
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


def slug_to_name(slug):
    SQL = "SELECT name FROM community_summary WHERE slug=%s"
    rec = gittip.db.one(SQL, (slug,))
    return None if rec is None else rec['name']


def get_list_for(user):
    if user is None or (hasattr(user, 'ANON') and user.ANON):
        return list(gittip.db.all("""

            SELECT max(name) AS name
                 , slug
                 , count(*) AS nmembers
              FROM current_communities
          GROUP BY slug
          ORDER BY nmembers DESC, slug

        """))
    else:
        return list(gittip.db.all("""

            SELECT max(name) AS name
                 , slug
                 , count(*) AS nmembers
                 , bool_or(participant = %s) AS is_member
              FROM current_communities
          GROUP BY slug
          ORDER BY nmembers ASC, slug

        """, (user.username,)))


class Community(db.Model):
    __tablename__ = 'community_summary'

    name = Column(Text)
    slug = Column(Text, primary_key=True)
    nmembers = Column(BigInteger)

    def check_membership(self, user):
        return gittip.db.one("""

        SELECT * FROM current_communities WHERE slug=%s AND participant=%s

        """, (self.slug, user.username)) is not None
