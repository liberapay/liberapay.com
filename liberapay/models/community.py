import re

from postgres.orm import Model
from psycopg2 import IntegrityError

from liberapay.exceptions import CommunityAlreadyExists, InvalidCommunityName


name_maxlength = 40
name_allowed_chars_pattern = r'\w\.-'
name_pattern = r'^[%s]{1,%s}$' % (name_allowed_chars_pattern, name_maxlength)
name_re = re.compile(name_pattern, re.U)
normalize_re = re.compile(r'[^%s]+' % name_allowed_chars_pattern, re.U)

def normalize(name):
    return normalize_re.sub('-', name).strip('-')


class Community(Model):

    typname = "communities"

    @classmethod
    def create(cls, name, creator_id):
        if name_re.match(name) is None:
            raise InvalidCommunityName(name)
        try:
            return cls.db.one("""
                INSERT INTO communities
                            (name, creator)
                     VALUES (%s, %s)
                  RETURNING communities.*::communities
            """, (name, creator_id))
        except IntegrityError:
            raise CommunityAlreadyExists(name)

    @classmethod
    def get_list(cls):
        """Return a listing of communities.
        """
        return cls.db.all("""
            SELECT c.*::communities
              FROM communities c
          ORDER BY nmembers DESC, name
        """)

    @classmethod
    def from_name(cls, name):
        if name_re.match(name) is None:
            return
        return cls.db.one("""
            SELECT c.*::communities FROM communities c WHERE lower(name)=%s;
        """, (name.lower(),))

    def get_members(self, limit=None, offset=None):
        return self.db.all("""
            SELECT p.*::participants
              FROM community_memberships cm
              JOIN participants p ON p.id = cm.participant
             WHERE cm.community = %s
               AND cm.is_on
          ORDER BY cm.ctime
             LIMIT %s
            OFFSET %s;
        """, (self.id, limit, offset))

    def check_status(self, table, participant):
        assert table in ('memberships', 'subscriptions')
        return self.db.one("""
            SELECT is_on
              FROM community_{0}
             WHERE community=%s AND participant=%s
        """.format(table), (self.id, participant.id))
