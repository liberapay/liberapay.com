import re

from postgres.orm import Model


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


def slug_to_name(db, slug):
    """Given a slug like ``python``, return a name like ``Python``.

    :database: One SELECT, one row

    """
    SQL = "SELECT name FROM community_summary WHERE slug=%s"
    return db.one(SQL, (slug,))


def get_list_for(db, username):
    """Return a listing of communities.

    :database: One SELECT, multiple rows

    """
    if username is None:
        member_test = ''
        sort_order = 'DESC'
        params = ()
    else:
        member_test = 'AND participant = %s'
        sort_order = 'ASC'
        params = (username,)

    return db.all("""

        SELECT max(name) AS name
             , slug
             , count(*) AS nmembers
          FROM current_communities
         WHERE is_member {0}
      GROUP BY slug
      ORDER BY nmembers {1}, slug

    """.format(member_test, sort_order), params)

class Community(Model):
    """Model a community on Gittip.
    """

    typname = "community_summary"

    @classmethod
    def from_slug(cls, slug):
        return cls.db.one("""
            SELECT community_summary.*::community_summary
            FROM community_summary WHERE slug=%s;
        """, (slug,))

    def get_members(self, limit=None, offset=None):
        return self.db.all("""
            SELECT p.*::participants
              FROM current_communities c
              JOIN participants p ON p.username = c.participant
             WHERE c.slug = %s
               AND is_member
          ORDER BY c.ctime
             LIMIT %s
            OFFSET %s;
        """, (self.slug, limit, offset))

    def check_membership(self, participant):
        return self.db.one("""
            SELECT * FROM current_communities WHERE slug=%s AND participant=%s
        """, (self.slug, participant.username))
