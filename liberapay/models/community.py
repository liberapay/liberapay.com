import re
import unicodedata

from postgres.orm import Model
from psycopg2 import IntegrityError
from confusable_homoglyphs import confusables

from liberapay.exceptions import CommunityAlreadyExists, InvalidCommunityName


name_maxlength = 40
name_allowed_chars_pattern = r'\w\.\+-'
name_pattern = r'^[%s]{1,%s}$' % (name_allowed_chars_pattern, name_maxlength)
name_re = re.compile(name_pattern, re.U)
normalize_re = re.compile(r'[^%s]+' % name_allowed_chars_pattern, re.U)

def normalize(name):
    return normalize_re.sub('_', name).strip('_')


class _Community(Model):
    typname = "communities"


class Community(Model):

    typname = "community_with_participant"

    subtitle_maxlength = 120
    sidebar_maxlength = 4096

    def __init__(self, raw_record):
        record = raw_record['c'].__dict__
        record['participant'] = raw_record['p']
        super(Community, self).__init__(record)

    @classmethod
    def create(cls, name, creator_id, lang='mul'):
        name = unicodedata.normalize('NFKC', name)
        if name_re.match(name) is None:
            raise InvalidCommunityName(name)

        try:
            with cls.db.get_cursor() as cursor:
                all_names = cursor.all("""
                    SELECT name
                    FROM communities
                    """)
                for existing_name in all_names:
                    if cls._unconfusable(name) == cls._unconfusable(existing_name):
                        raise CommunityAlreadyExists

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

    def check_membership_status(self, participant):
        return self.db.one("""
            SELECT is_on
              FROM community_memberships
             WHERE community=%s AND participant=%s
        """, (self.id, participant.id))

    @property
    def nsubscribers(self):
        return self.participant.nsubscribers

    @staticmethod
    def _unconfusable(name):
        unconfusable_name = ''
        for c in name:
            confusable = confusables.is_confusable(c, preferred_aliases=['COMMON', 'LATIN'])
            if confusable:
                # if the character is confusable we replace it with the first prefered alias
                c = confusable[0]['homoglyphs'][0]['c']
            unconfusable_name += c
        return unconfusable_name
