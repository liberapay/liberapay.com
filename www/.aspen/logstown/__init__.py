import logging
import os
import urlparse

import psycopg2
import psycopg2.extras
import psycopg2.pool


log = logging.getLogger('logstown.db')


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
    global db
    url = os.environ['SHARED_DATABASE_URL']
    parsed = urlparse.urlparse(url)
    foo, bar = parsed.netloc.split('@')
    user, password = foo.split(':')
    host, port = bar.split(':')
    dsn = "dbname=%s user=%s password=%s host=%s port=%s"
    dsn %= (parsed.path[1:], user, password, host, port)
    db = PostgresManager(dsn)

