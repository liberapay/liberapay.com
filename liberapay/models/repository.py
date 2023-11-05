from time import sleep

from oauthlib.oauth2 import InvalidGrantError, TokenExpiredError
from postgres.orm import Model

from liberapay.cron import logger
from liberapay.elsewhere._base import ElsewhereError
from liberapay.models.account_elsewhere import UnableToRefreshAccount
from liberapay.models.participant import Participant
from liberapay.utils import utcnow
from liberapay.website import website


class Repository(Model):

    typname = "repositories"

    @classmethod
    def from_repo_info(cls, info):
        r = object.__new__(cls)
        _setattr = object.__setattr__
        for attr in cls.attnames:
            _setattr(r, attr, getattr(info, attr, None))
        return r

    @property
    def url(self):
        platform = getattr(website.platforms, self.platform)
        return platform.repo_url.format(**self.__dict__)

    def get_owner(self):
        return self.db.one("""
            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform = %s
               AND domain = %s
               AND user_id = %s
        """, (self.platform, '', str(self.owner_id)))


def upsert_repos(cursor, repos, participant, info_fetched_at):
    if not repos:
        return repos
    r = []
    for repo in repos:
        if not repo.owner_id or not repo.last_update:
            continue
        repo.participant = participant.id
        repo.info_fetched_at = info_fetched_at
        cols, vals = zip(*repo.__dict__.items())
        on_conflict_set = ','.join('{0}=excluded.{0}'.format(col) for col in cols)
        cols = ','.join(cols)
        placeholders = ('%s,'*len(vals))[:-1]
        cursor.run("""
            DELETE FROM repositories
             WHERE platform = %s
               AND slug = %s
               AND remote_id <> %s
        """, (repo.platform, repo.slug, repo.remote_id))
        r.append(cursor.one("""
            INSERT INTO repositories
                        ({0})
                 VALUES ({1})
            ON CONFLICT (platform, remote_id) DO UPDATE
                    SET {2}
              RETURNING repositories
        """.format(cols, placeholders, on_conflict_set), vals))
    return r


def refetch_repos():
    # Note: the rate_limiting table is used to avoid blocking on errors
    repos = website.db.all("""
        WITH repo AS (
            SELECT r.*
              FROM repositories r
             WHERE r.info_fetched_at < now() - interval '6 days'
               AND (r.last_fetch_attempt IS NULL OR r.last_fetch_attempt < (current_timestamp - interval '1 day'))
               AND r.participant IS NOT NULL
               AND r.show_on_profile
          ORDER BY r.info_fetched_at ASC
             LIMIT 1
        )
        UPDATE repositories
           SET last_fetch_attempt = current_timestamp
         WHERE participant = (SELECT repo.participant FROM repo)
           AND platform = (SELECT repo.platform FROM repo)
     RETURNING participant, platform
    """)
    if not repos:
        return

    participant_id, platform = repos[-1]
    participant = Participant.from_id(participant_id)
    accounts = participant.get_accounts_elsewhere(platform)
    if not accounts:
        return
    for account in accounts:
        if account.missing_since is not None:
            continue
        _refetch_repos_for_account(participant, account)


def _refetch_repos_for_account(participant, account):
    sess = account.get_auth_session()
    logger.debug(
        "Refetching profile data for participant ~%s from %s account %s" %
        (participant.id, account.platform, account.user_id)
    )
    try:
        account = account.refresh_user_info()
    except (ElsewhereError, UnableToRefreshAccount) as e:
        logger.debug(f"The refetch failed: {e.__class__.__name__}: {e}")
    sleep(1)

    logger.debug(
        "Refetching repository data for participant ~%s from %s account %s" %
        (participant.id, account.platform, account.user_id)
    )
    start_time = utcnow()
    try:
        with website.db.get_cursor() as cursor:
            next_page = None
            for i in range(10):
                r = account.platform_data.get_repos(account, page_url=next_page, sess=sess)
                upsert_repos(cursor, r[0], participant, utcnow())
                next_page = r[2].get('next')
                if not next_page:
                    break
                sleep(1)
            deleted_count = cursor.one("""
                WITH deleted AS (
                         DELETE FROM repositories
                          WHERE participant = %s
                            AND platform = %s
                            AND info_fetched_at < %s
                      RETURNING id
                     )
                SELECT count(*) FROM deleted
            """, (participant.id, account.platform, start_time))
            event_type = 'fetch_repos:%s' % account.id
            payload = dict(partial_list=bool(next_page), deleted_count=deleted_count)
            participant.add_event(cursor, event_type, payload)
            cursor.run("""
                DELETE FROM events
                 WHERE participant = %s
                   AND type = %s
                   AND (NOT payload ? 'deleted_count' OR payload->'deleted_count' = '0')
                   AND ts < (current_timestamp - interval '6 days')
            """, (participant.id, event_type))
    except (InvalidGrantError, TokenExpiredError) as e:
        logger.debug("The refetch failed: %s" % e)
        return
