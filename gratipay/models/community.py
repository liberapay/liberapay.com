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


def get_list_for(db, participant_id):
    """Return a listing of communities.

    :database: One SELECT, multiple rows

    """
    if participant_id is None:
        return db.all("""
            SELECT c.*
              FROM communities c
          ORDER BY nmembers DESC, slug
        """)
    else:
        return db.all("""
            SELECT c.*
              FROM current_community_members ccm
              JOIN communities c ON c.slug = ccm.slug
             WHERE ccm.is_member AND ccm.participant = %s
          ORDER BY c.nmembers ASC, c.slug
        """, (participant_id,))

class Community(Model):
    """Model a community on Gratipay.
    """

    typname = "communities"

    @classmethod
    def from_slug(cls, slug):
        return cls.db.one("""
            SELECT c.*::communities FROM communities c WHERE slug=%s;
        """, (slug,))

    def get_members(self, limit=None, offset=None):
        return self.db.all("""
            SELECT p.*::participants
              FROM current_community_members c
              JOIN participants p ON p.id = c.participant
             WHERE c.slug = %s
               AND c.is_member
               AND p.is_suspicious IS NOT true
          ORDER BY c.ctime
             LIMIT %s
            OFFSET %s;
        """, (self.slug, limit, offset))

    def check_membership(self, participant):
        return self.db.one("""
            SELECT is_member
              FROM current_community_members
             WHERE slug=%s AND participant=%s
        """, (self.slug, participant.id))
