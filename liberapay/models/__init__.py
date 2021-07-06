from contextlib import contextmanager
import re
import sys
import traceback

from postgres import Postgres
from postgres.cursors import SimpleCursorBase
import psycopg2
from psycopg2 import IntegrityError, InterfaceError, ProgrammingError
from psycopg2_pool import ThreadSafeConnectionPool

from liberapay.constants import RATE_LIMITS
from liberapay.website import website


class CustomConnectionPool(ThreadSafeConnectionPool):

    __slots__ = ('okay',)

    def __init__(self, *a, **kw):
        self.okay = None
        super().__init__(*a, **kw)

    def _connect(self, *a, **kw):
        try:
            r = super()._connect(*a, **kw)
            self.okay = True
            return r
        except psycopg2.Error:
            self.okay = False
            raise


class DB(Postgres):

    def __init__(self, *a, **kw):
        kw.setdefault('pool_class', CustomConnectionPool)
        super().__init__(*a, **kw)

    def __bool__(self):
        return self.pool.okay

    def self_check(self):
        with self.get_cursor() as cursor:
            check_db(cursor)


def check_db(cursor):
    """Runs all available self checks on the given cursor.
    """
    _check_tips(cursor)
    _check_sum_of_payin_transfers(cursor)


def _check_tips(cursor):
    """
    Checks that there are no rows in tips with duplicate (tipper, tippee, mtime).

    https://github.com/gratipay/gratipay.com/issues/1704
    """
    conflicting_tips = cursor.one("""
        SELECT count(*)
          FROM
             (
                SELECT * FROM tips
                EXCEPT
                SELECT DISTINCT ON(tipper, tippee, mtime) *
                  FROM tips
              ORDER BY tipper, tippee, mtime
              ) AS foo
    """)
    assert conflicting_tips == 0, conflicting_tips


def _check_sum_of_payin_transfers(cursor):
    """Check that the sum of a payin's transfers matches its net amount.

    Some transfers can fail and be replaced by new ones, so the check ignores
    failed transfers, unless the payin has been refunded (because sometimes a
    failed transfer can't be retried so the payin is refunded instead).
    """
    l = cursor.all("""
        SELECT pi.id AS payin_id, pi.amount_settled, pi.fee
             , (pi.amount_settled - pi.fee) AS net_amount
             , pi.refunded_amount
             , sum(pt.amount) AS transfers_sum
          FROM payin_transfers pt
          JOIN payins pi ON pi.id = pt.payin
         WHERE pi.amount_settled IS NOT NULL
      GROUP BY pi.id
        HAVING pi.refunded_amount IS NULL AND
               (pi.amount_settled - pi.fee) <> (sum(pt.amount) FILTER (WHERE pt.status <> 'failed'))
            OR pi.refunded_amount IS NOT NULL AND
               (pi.amount_settled - pi.fee) <> sum(pt.amount);
    """)
    assert len(l) == 0, "payin transfers are out of whack:\n" + '\n'.join(str(r) for r in l)


def run_migrations(db):
    naive_re = re.compile(r';\n(?=[A-Z])')
    v = 0
    db_meta = db.one("SELECT to_regclass('db_meta')")
    if db_meta:
        v = db.one("SELECT value FROM db_meta WHERE key = 'schema_version'")
    migrations = open('sql/migrations.sql').read().split('\n\n-- migration #')
    for m in migrations[1:]:
        n, sql = m.split('\n', 1)
        n = int(n)
        if v >= n:
            continue
        print('Running migration #%s...' % n)
        with db.get_cursor(autocommit=True) as cursor:
            # Some schema updates can't run inside a transaction, so we run the
            # migration outside of any transaction
            try:
                for query in naive_re.split(sql):
                    cursor.run(query)
            except (IntegrityError, ProgrammingError):
                traceback.print_exc()
                r = input('Have you already run this migration? (y/N) ')
                if r.lower() != 'y':
                    sys.exit(1)
        db.run("""
            UPDATE db_meta
               SET value = '%s'::jsonb
             WHERE key = 'schema_version'
        """, (n,))
    if db.one("SELECT count(*) FROM app_conf") == 0:
        print('Running sql/app-conf-defaults.sql...')
        db.run(open('sql/app-conf-defaults.sql').read())
    print('All done.' if n != v else 'No new migrations found.')
    return n - v


def render(db, query, args=None):
    data = db.all(query, args)
    if len(data) == 0:
        return
    r = ''
    widths = list(len(k) for k in data[0]._fields)
    for row in data:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(str(v).replace('\n', '\\n')))
    for k, w in zip(data[0]._fields, widths):
        r += "{0:{width}} | ".format(str(k), width=w)
    r += '\n'
    for row in data:
        for v, w in zip(row, widths):
            r += "{0:{width}} | ".format(str(v).replace('\n', '\\n'), width=w)
        r += '\n'
    return r

DB.render = SimpleCursorBase.render = render


def show_table(db, table):
    assert re.match(r'^\w+$', table)
    print('\n{:=^80}'.format(table))
    r = render(db, 'select * from '+table)
    if r:
        print(r, end='')

DB.show_table = SimpleCursorBase.show_table = show_table


def hit_rate_limit(db, key_prefix, key_unique, exception=None):
    try:
        cap, period = RATE_LIMITS[key_prefix]
        key = '%s:%s' % (key_prefix, key_unique)
        r = db.one("SELECT hit_rate_limit(%s, %s, %s)", (key, cap, period))
    except Exception as e:
        website.tell_sentry(e)
        return -1
    if r is None and exception is not None:
        website.logger.warning(f"rate limit counter {key!r} is maxed out")
        raise exception(key_unique)
    return r

DB.hit_rate_limit = SimpleCursorBase.hit_rate_limit = hit_rate_limit


def decrement_rate_limit(db, key_prefix, key_unique):
    try:
        cap, period = RATE_LIMITS[key_prefix]
        key = '%s:%s' % (key_prefix, key_unique)
        return db.one("SELECT decrement_rate_limit(%s, %s, %s)", (key, cap, period))
    except Exception as e:
        website.tell_sentry(e)
        return -1

DB.decrement_rate_limit = SimpleCursorBase.decrement_rate_limit = decrement_rate_limit


def clean_up_counters(db):
    n = 0
    for key_prefix, (cap, period) in RATE_LIMITS.items():
        n += db.one("SELECT clean_up_counters(%s, %s)", (key_prefix+':%', period))
    return n

DB.clean_up_counters = clean_up_counters


DB_LOCKS = {
    'payday': 1,
    'dispute_callback': 2,
}

@contextmanager
def acquire_db_lock(db, lock_name, blocking=True):
    lock_id = DB_LOCKS[lock_name]
    with db.get_cursor(autocommit=True) as cursor:
        if blocking:
            cursor.run("SELECT pg_advisory_lock(%s)", (lock_id,))
        else:
            locked = cursor.one("SELECT pg_try_advisory_lock(%s)", (lock_id,))
            assert locked, "failed to acquire the %s lock" % lock_name
        try:
            yield
        finally:
            try:
                cursor.run("SELECT pg_advisory_unlock(%s)", (lock_id,))
            except InterfaceError:
                pass

DB.lock = acquire_db_lock


if __name__ == '__main__':
    from liberapay import wireup
    db = wireup.minimal_chain.run(**website.__dict__)['db']
    print('Checking DB...')
    try:
        db.self_check()
    except Exception:
        traceback.print_exc()
        r = input('The DB self-check failed, proceed anyway? (y/N) ')
        if r != 'y':
            sys.exit(1)
    r = run_migrations(db)
    if r:
        print('Checking DB...')
        db.self_check()
