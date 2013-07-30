import os
import threading
import time

import gittip
import gittip.wireup
import gittip.authentication
import gittip.orm
import gittip.csrf
import gittip.cache_static
import gittip.models.participant
from aspen import log_dammit


version_file = os.path.join(website.www_root, 'version.txt')
__version__ = open(version_file).read().strip()
website.version = os.environ['__VERSION__'] = __version__


website.renderer_default = "tornado"


gittip.wireup.canonical()
gittip.wireup.db()
gittip.wireup.billing()
gittip.wireup.username_restrictions(website)
gittip.wireup.sentry(website)
gittip.wireup.mixpanel(website)
gittip.wireup.nanswers()
gittip.wireup.nmembers(website)
gittip.wireup.envvars(website)


# Up the threadpool size: https://github.com/gittip/www.gittip.com/issues/1098
def up_minthreads(website):
    # Discovered the following API by inspecting in pdb and browsing source.
    # This requires network_engine.bind to have already been called.
    website.network_engine.cheroot_server.requests.min = \
                                                 int(os.environ['MIN_THREADS'])

website.hooks.startup.insert(0, up_minthreads)


website.hooks.inbound_early += [ gittip.canonize
                               , gittip.configure_payments
                               , gittip.authentication.inbound
                               , gittip.csrf.inbound
                                ]

website.hooks.inbound_core += [gittip.cache_static.inbound]

website.hooks.outbound += [ gittip.authentication.outbound
                          , gittip.csrf.outbound
                          , gittip.orm.rollback
                          , gittip.cache_static.outbound
                           ]


def add_stuff(request):
    from gittip.elsewhere import bitbucket, github, twitter, bountysource
    from gittip.utils import with_mine
    request.context['__version__'] = __version__
    request.context['username'] = None
    request.context['bitbucket'] = bitbucket
    request.context['github'] = github
    request.context['twitter'] = twitter
    request.context['bountysource'] = bountysource
    request.context['with_mine'] = with_mine

website.hooks.inbound_early += [add_stuff]


# The homepage wants expensive queries. Let's periodically select into an
# intermediate table.

UPDATE_HOMEPAGE_EVERY = int(os.environ['UPDATE_HOMEPAGE_EVERY'])
def update_homepage_queries():
    while 1:
        with gittip.db.get_transaction() as txn:
            log_dammit("updating homepage queries")
            start = time.time()
            txn.execute("""

            DROP TABLE IF EXISTS _homepage_new_participants;
            CREATE TABLE _homepage_new_participants AS
                  SELECT username, claimed_time FROM (
                      SELECT DISTINCT ON (p.username)
                             p.username
                           , claimed_time
                        FROM participants p
                        JOIN elsewhere e
                          ON p.username = participant
                       WHERE claimed_time IS NOT null
                         AND is_suspicious IS NOT true
                         ) AS foo
                ORDER BY claimed_time DESC;

            DROP TABLE IF EXISTS _homepage_top_givers;
            CREATE TABLE _homepage_top_givers AS
                SELECT tipper AS username, anonymous, sum(amount) AS amount
                  FROM (    SELECT DISTINCT ON (tipper, tippee)
                                   amount
                                 , tipper
                              FROM tips
                              JOIN participants p ON p.username = tipper
                              JOIN participants p2 ON p2.username = tippee
                              JOIN elsewhere ON elsewhere.participant = tippee
                             WHERE p.last_bill_result = ''
                               AND p.is_suspicious IS NOT true
                               AND p2.claimed_time IS NOT NULL
                               AND elsewhere.is_locked = false
                          ORDER BY tipper, tippee, mtime DESC
                          ) AS foo
                  JOIN participants p ON p.username = tipper
                 WHERE is_suspicious IS NOT true
              GROUP BY tipper, anonymous
              ORDER BY amount DESC;

            DROP TABLE IF EXISTS _homepage_top_receivers;
            CREATE TABLE _homepage_top_receivers AS
                SELECT tippee AS username, claimed_time, sum(amount) AS amount
                  FROM (    SELECT DISTINCT ON (tipper, tippee)
                                   amount
                                 , tippee
                              FROM tips
                              JOIN participants p ON p.username = tipper
                              JOIN elsewhere ON elsewhere.participant = tippee
                             WHERE last_bill_result = ''
                               AND elsewhere.is_locked = false
                               AND is_suspicious IS NOT true
                               AND claimed_time IS NOT null
                          ORDER BY tipper, tippee, mtime DESC
                          ) AS foo
                  JOIN participants p ON p.username = tippee
                 WHERE is_suspicious IS NOT true
              GROUP BY tippee, claimed_time
              ORDER BY amount DESC;

            DROP TABLE IF EXISTS homepage_new_participants;
            ALTER TABLE _homepage_new_participants
              RENAME TO homepage_new_participants;

            DROP TABLE IF EXISTS homepage_top_givers;
            ALTER TABLE _homepage_top_givers
              RENAME TO homepage_top_givers;

            DROP TABLE IF EXISTS homepage_top_receivers;
            ALTER TABLE _homepage_top_receivers
              RENAME TO homepage_top_receivers;

            """)
            end = time.time()
            elapsed = end - start
            log_dammit("updated homepage queries in %.2f seconds" % elapsed)
        time.sleep(UPDATE_HOMEPAGE_EVERY)

homepage_updater = threading.Thread(target=update_homepage_queries)
homepage_updater.daemon = True
homepage_updater.start()
