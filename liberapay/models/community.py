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
    return normalize_re.sub('_', name).strip('_')


class Community(Model):

    typname = "community_with_participant"

    subtitle_maxlength = 120
    sidebar_maxlength = 4096

    @classmethod
    def create(cls, name, creator_id, lang='mul'):
        if name_re.match(name) is None:
            raise InvalidCommunityName(name)
        try:
            with cls.db.get_cursor() as cursor:
                p_id = cursor.one("""
                    INSERT INTO participants
                                (kind, status, join_time)
                         VALUES ('community', 'active', now())
                      RETURNING id
                """)
                return cursor.one("""
                    INSERT INTO communities
                                (name, creator, lang, participant)
                         VALUES (%s, %s, %s, %s)
                      RETURNING communities.*::community_with_participant
                """, (name, creator_id, lang, p_id))
        except IntegrityError:
            raise CommunityAlreadyExists(name)

    @staticmethod
    def get_list(db):
        """Return a listing of communities.
        """
        return db.all("""
            SELECT c.*, replace(name, '_', ' ') AS pretty_name
              FROM communities c
          ORDER BY nmembers DESC, name
        """)

    @classmethod
    def from_name(cls, name):
        if name_re.match(name) is None:
            return
        return cls.db.one("""
            SELECT c.*::community_with_participant
              FROM communities c
             WHERE lower(name)=%s
        """, (name.lower(),))

    @property
    def pretty_name(self):
        return self.name.replace('_', ' ')

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
