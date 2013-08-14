import re

import gittip


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
    return gittip.db.one_or_zero(SQL, (slug,))


def get_list_for(user):
    """Return a listing of communities.

    :database: One SELECT, multiple rows

    """
    if user is None or user.ANON:
        member_test = "false"
        sort_order = 'DESC'
        params = ()
    else:
        member_test = "bool_or(participant = %s)"
        sort_order = 'ASC'
        params = (user.username,)

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

    def check_membership(self, user):
        return self.db.one_or_zero("""

        SELECT * FROM current_communities WHERE slug=%s AND participant=%s

        """, (self.slug, user.username)) is not None


def typecast(request):
    pass
