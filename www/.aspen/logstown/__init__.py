import logging
import os
import urlparse

import psycopg2
import psycopg2.extras
import psycopg2.pool
import samurai.config


log = logging.getLogger('logstown.db')


canonical_scheme = os.environ['CANONICAL_SCHEME']
canonical_host = os.environ['CANONICAL_HOST']

def canonize(request):
    scheme_bad = request.urlparts.scheme != canonical_scheme
    host_bad = request.headers.one('Host') != canonical_host
    if scheme_bad or host_bad:
        url = '%s://%s/' % (canonical_scheme, canonical_host)
        old = '%s://%s/' % (request.urlparts.scheme, request.headers.one('Host'))
        print "redirecting to", url, "from", old
        pprint.pprint(os.environ)
        request.redirect(url, permanent=True)


class MissedConnection:
    """This signals that a database connection was set to the empty string.
    """
    def __repr__(self):
        return "<MissedConnection>"
MissedConnection = MissedConnection() # singleton

class PostgresManager(object):
    """Manage connections to a PostgreSQL datastore. One per process.
    """

    pool = None

    def __init__(self, connection_spec):
        self.connection_spec = connection_spec
        log.info('wiring up logstown.db: %s' % self.connection_spec)

    def check_configuration(self):
        if self.connection_spec is MissedConnection:
            msg = "logstown.db is not configured."
            raise RuntimeError(msg)

    def execute(self, *a, **kw):
        """This is a convenience function.
        """
        if self.pool is None: # lazy
            self.check_configuration()
            # http://www.initd.org/psycopg/docs/pool.html
            dsn = self.connection_spec
            self.pool = psycopg2.pool.ThreadedConnectionPool(1, 10, dsn)
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

db = None 
def startup(website):
    """Set up db and cc.
    """

    # Database
    # ========
    # Adapt from URL (per Heroku) to DSN (per psycopg2).

    global db
    url = os.environ['SHARED_DATABASE_URL']
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
    db = PostgresManager(dsn)


    # Samurai
    # =======

    samurai.config.merchant_key = os.environ['SAMURAI_MERCHANT_KEY']
    samurai.config.merchant_password = os.environ['SAMURAI_MERCHANT_PASSWORD']
    samurai.config.processor_token = os.environ['SAMURAI_PROCESSOR_TOKEN']
