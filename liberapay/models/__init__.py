from __future__ import print_function

from contextlib import contextmanager
import re
import sys
import traceback

from six.moves import input

from postgres import Postgres
from postgres.cursors import SimpleCursorBase
from psycopg2 import IntegrityError, ProgrammingError
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


@contextmanager
def just_yield(obj):
    yield obj


class DB(Postgres):

    def get_cursor(self, cursor=None, **kw):
        if cursor:
            if kw:
                raise ValueError('cannot change options when reusing a cursor')
            return just_yield(cursor)
        return super(DB, self).get_cursor(**kw)

    def self_check(self):
        with self.get_cursor() as cursor:
            check_db(cursor)


def check_db(cursor):
    """Runs all available self checks on the given cursor.
    """
    _check_balances_against_transactions(cursor)
    _check_tips(cursor)
    _check_bundles_against_balances(cursor)
    _check_bundles_grouped_by_origin_against_exchanges(cursor)
    _check_bundles_grouped_by_withdrawal_against_exchanges(cursor)


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


def _check_balances_against_transactions(cursor):
    """
    Recalculates balances for all participants from transfers and exchanges.

    https://github.com/gratipay/gratipay.com/issues/1118
    """
    b = cursor.all("""
        select p.id, expected, balance as actual
          from (
            select id, sum(a) as expected
              from (
                      select participant as id, sum(amount - (CASE WHEN (fee < 0) THEN fee ELSE 0 END)) as a
                        from exchanges
                       where amount > 0
                         and status = 'succeeded'
                    group by participant

                       union all

                      select participant as id, sum(amount - (CASE WHEN (fee > 0) THEN fee ELSE 0 END)) as a
                        from exchanges
                       where amount < 0
                         and status <> 'failed'
                    group by participant

                       union all

                      select tipper as id, sum(-amount) as a
                        from transfers
                       where status = 'succeeded'
                    group by tipper

                       union all

                      select tippee as id, sum(amount) as a
                        from transfers
                       where status = 'succeeded'
                    group by tippee
                    ) as foo
            group by id
          ) as foo2
        join participants p on p.id = foo2.id
        where expected <> p.balance
    """)
    assert len(b) == 0, "conflicting balances:\n" + '\n'.join(str(r) for r in b)


def _check_bundles_against_balances(cursor):
    """Check that balances and cash bundles are coherent.
    """
    b = cursor.all("""
        SELECT owner, bundles_total, balance
          FROM (
              SELECT owner, sum(amount) AS bundles_total
                FROM cash_bundles b
            GROUP BY owner
          ) foo
          JOIN participants p ON p.id = owner
         WHERE bundles_total <> balance
    """)
    assert len(b) == 0, "bundles are out of whack:\n" + '\n'.join(str(r) for r in b)


def _check_bundles_grouped_by_origin_against_exchanges(cursor):
    """Check that bundles grouped by origin are coherent with exchanges.
    """
    l = cursor.all("""
        WITH r AS (
        SELECT e.id as e_id
             , (CASE WHEN (e.amount < 0 OR e.status <> 'succeeded' OR (
                              e.amount > 0 AND e.refund_ref IS NOT NULL
                          ))
                     THEN 0
                     ELSE e.amount - (CASE WHEN (e.fee < 0) THEN e.fee ELSE 0 END)
                END) as total_expected
             , (COALESCE(in_wallets, 0) + COALESCE(withdrawn, 0)) as total_found
             , in_wallets
             , withdrawn
          FROM exchanges e
          LEFT JOIN (
                  SELECT b.origin, sum(b.amount) as in_wallets
                    FROM cash_bundles b
                   WHERE b.withdrawal IS NULL
                GROUP BY b.origin
               ) AS b ON b.origin = e.id
          LEFT JOIN (
                  SELECT b2.origin, sum(b2.amount) as withdrawn
                    FROM cash_bundles b2
                   WHERE b2.withdrawal IS NOT NULL
                GROUP BY b2.origin
               ) AS b2 ON b2.origin = e.id
        )
        SELECT *
          FROM r
         WHERE total_expected <> total_found
      ORDER BY e_id
    """)
    assert len(l) == 0, "bundles are out of whack:\n" + '\n'.join(str(r) for r in l)


def _check_bundles_grouped_by_withdrawal_against_exchanges(cursor):
    """Check that bundles grouped by withdrawal are coherent with exchanges.
    """
    l = cursor.all("""
        WITH r AS (
        SELECT e.id as e_id
             , (CASE WHEN (e.amount > 0 OR e.status = 'failed' OR EXISTS (
                              SELECT 1
                                FROM exchanges e2
                               WHERE e2.refund_ref = e.id
                                 AND e2.status = 'succeeded'
                          ))
                     THEN 0
                     ELSE -e.amount + (CASE WHEN (e.fee < 0) THEN 0 ELSE e.fee END)
                END) as total_expected
             , COALESCE(withdrawn, 0) as total_found
          FROM exchanges e
          LEFT JOIN (
                  SELECT b.withdrawal, sum(b.amount) as withdrawn
                    FROM cash_bundles b
                GROUP BY b.withdrawal
               ) AS b ON b.withdrawal = e.id
        )
        SELECT *
          FROM r
         WHERE total_expected <> total_found
      ORDER BY e_id
    """)
    assert len(l) == 0, "bundles are out of whack:\n" + '\n'.join(str(r) for r in l)


def run_migrations(db):
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
        with db.get_connection() as conn:
            # Some schema updates can't run inside a transaction, so we run the
            # migration outside of any transaction
            old_isolation_level = conn.isolation_level
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            try:
                cursor = conn.cursor()
                cursor.execute(sql)
            except (IntegrityError, ProgrammingError):
                traceback.print_exc()
                r = input('Have you already run this migration? (y/N) ')
                if r.lower() != 'y':
                    sys.exit(1)
            finally:
                conn.set_isolation_level(old_isolation_level)
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
            widths[i] = max(widths[i], len(str(v)))
    for k, w in zip(data[0]._fields, widths):
        r += "{0:{width}} | ".format(str(k), width=w)
    r += '\n'
    for row in data:
        for v, w in zip(row, widths):
            r += "{0:{width}} | ".format(str(v), width=w)
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


if __name__ == '__main__':
    from liberapay import wireup
    db = wireup.minimal_algorithm.run()['db']
    print('Checking DB...')
    db.self_check()
    r = run_migrations(db)
    if r:
        print('Checking DB...')
        db.self_check()
