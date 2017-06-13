from __future__ import absolute_import, division, print_function, unicode_literals

from postgres.orm import Model

from liberapay.utils import utcnow
from liberapay.website import website


class Repository(Model):

    typname = "repositories"

    @property
    def url(self):
        platform = getattr(website.platforms, self.platform)
        return platform.repo_url.format(**self.__dict__)


def upsert_repos(cursor, repos, participant):
    if not repos:
        return repos
    r = []
    for repo in repos:
        repo.participant = participant.id
        repo.extra_info = json.dumps(repo.extra_info)
        repo.info_fetched_at = utcnow()
        cols, vals = zip(*repo.__dict__.items())
        on_conflict_set = ','.join('{0}=excluded.{0}'.format(col) for col in cols)
        cols = ','.join(cols)
        placeholders = ('%s,'*len(vals))[:-1]
        r.append(cursor.one("""
            INSERT INTO repositories
                        ({0})
                 VALUES ({1})
            ON CONFLICT (platform, remote_id) DO UPDATE
                    SET {2}
              RETURNING repositories
        """.format(cols, placeholders, on_conflict_set), vals))
    return r
