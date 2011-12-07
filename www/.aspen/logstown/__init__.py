import logging
import os
import urlparse
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool as ConnectionPool
import samurai.config


log = logging.getLogger('logstown')


# canonizer
# =========

class X: pass
canonical_scheme = os.environ['CANONICAL_SCHEME']
canonical_host = os.environ['CANONICAL_HOST']

def canonize(request):
    """Enforce a certain scheme and hostname. Store these on request as well.
    """
    scheme = request.environ.get('HTTP_X_FORWARDED_PROTO', 'http') # per Heroku
    host = request.headers.one('Host')
    bad_scheme = scheme != canonical_scheme
    bad_host = host != canonical_host
    if bad_scheme or bad_host:
        url = '%s://%s/' % (canonical_scheme, canonical_host)
        request.redirect(url, permanent=True)
    request.x = X()
    request.x.scheme = scheme
    request.x.host = host


# db
# ==

class PostgresConnection(psycopg2.extensions.connection):
    """Subclass to change transaction behavior.

    THE DBAPI 2.0 spec calls for transactions to be left open by default. I 
    don't think we want this.

    """

    def __init__(self, *a, **kw):
        psycopg2.extensions.connection.__init__(self, *a, **kw)
        self.autocommit = True # override dbapi2 default

class PostgresManager(object):
    """Manage connections to a PostgreSQL datastore. One per process.
    """

    def __init__(self, connection_spec):
        log.info('wiring up logstown.db: %s' % connection_spec)
        self.pool = ConnectionPool( minconn=1
                                  , maxconn=10
                                  , dsn=connection_spec
                                  , connection_factory=PostgresConnection
                                   )

    def execute(self, *a, **kw):
        """Execute the query and discard the results.
        """
        with self.get_cursor(*a, **kw) as cursor:
            pass

    def fetchone(self, *a, **kw):
        """Execute the query and yield the results.
        """
        with self.get_cursor(*a, **kw) as cursor:
            return cursor.fetchone()

    def fetchall(self, *a, **kw):
        """Execute the query and yield the results.
        """
        with self.get_cursor(*a, **kw) as cursor:
            for row in cursor:
                yield row

    def get_cursor(self, *a, **kw):
        """Execute the query and return a context manager wrapping the cursor.
        """
        return PostgresContextManager(self.pool, *a, **kw)

class PostgresContextManager:
    """Instantiated once per db access.
    """

    def __init__(self, pool, *a, **kw):
        self.pool = pool
        self.a = a
        self.kw = kw
        self.conn = None
    
    def __enter__(self):
        """Get a connection from the pool.
        """
        self.conn = self.pool.getconn()
        cursor_factory = psycopg2.extras.RealDictCursor
        cursor = self.conn.cursor(cursor_factory=cursor_factory)
        cursor.execute(*self.a, **self.kw)
        return cursor

    def __exit__(self, *a, **kw):
        """Put our connection back in the pool.
        """
        self.pool.putconn(self.conn)


# wireup
# ======

def url_to_dsn(url):
    """Heroku gives us an URL, psycopg2 wants a DSN. Convert!
    """
    parsed = urlparse.urlparse(url)
    dbname = parsed.path[1:] # /foobar
    # Why is the user:pass not parsed!? Is the scheme unrecognized?
    user_pass, host = parsed.netloc.split('@')
    user, password = user_pass.split(':')
    port = '5432' # postgres default port
    if ':' in host:
        host, port = host.split(':')
    dsn = "dbname=%s user=%s password=%s host=%s port=%s"
    dsn %= (dbname, user, password, host, port)
    return dsn

db = None 
def startup(website):
    """Set up db and cc.
    """
    global db
    url = os.environ['SHARED_DATABASE_URL']
    dsn = url_to_dsn(url)
    db = PostgresManager(dsn)

    samurai.config.merchant_key = os.environ['SAMURAI_MERCHANT_KEY']
    samurai.config.merchant_password = os.environ['SAMURAI_MERCHANT_PASSWORD']
    samurai.config.processor_token = os.environ['SAMURAI_PROCESSOR_TOKEN']
