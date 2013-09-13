import re

import gittip
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


def slug_to_name(slug):
    """Given a slug like ``python``, return a name like ``Python``.

    :database: One SELECT, one row

    """
    SQL = "SELECT name FROM community_summary WHERE slug=%s"
    return gittip.db.one(SQL, (slug,))


def get_list_for(username):
    """Return a listing of communities.

    :database: One SELECT, multiple rows

    """
    if username is None:
        member_test = "false"
        sort_order = 'DESC'
        params = ()
    else:
        member_test = "bool_or(participant = %s)"
        sort_order = 'ASC'
        params = (username,)

    return gittip.db.all("""

        SELECT max(name) AS name
             , slug
             , count(*) AS nmembers
             , {} AS is_member
          FROM current_communities
      GROUP BY slug
      ORDER BY nmembers {}, slug

    """.format(member_test, sort_order), params)


class Community(Model):
    """Model a community on Gittip.
    """

    typname = "community_summary"

    def check_membership(self, participant):
        return self.db.one("""

        SELECT * FROM current_communities WHERE slug=%s AND participant=%s

        """, (self.slug, participant.username)) is not None


def typecast(request):
    pass
