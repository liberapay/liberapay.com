import re

from postgres.orm import Model


name_pattern = re.compile(r'^[A-Za-z0-9,._ -]+$')
slugize_re = re.compile(r'^[ ,._-]+$')

def slugize(slug):
    """Convert a string to a string for an URL.
    """
    assert name_pattern.match(slug) is not None
    return slugize_re.sub('-', slug.lower()).strip('-')


class Community(Model):

    typname = "communities"

    @classmethod
    def get_list(cls):
        """Return a listing of communities.
        """
        return cls.db.all("""
            SELECT c.*::communities
              FROM communities c
          ORDER BY nmembers DESC, slug
        """)

    @classmethod
    def from_slug(cls, slug):
        return cls.db.one("""
            SELECT c.*::communities FROM communities c WHERE slug=%s;
        """, (slug,))

    def get_members(self, limit=None, offset=None):
        return self.db.all("""
            SELECT p.*::participants
              FROM community_members c
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
              FROM community_members
             WHERE slug=%s AND participant=%s
        """, (self.slug, participant.id))
