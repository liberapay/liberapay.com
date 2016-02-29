from __future__ import print_function

from contextlib import contextmanager
import re

from postgres import Postgres
from postgres.cursors import SimpleCursorBase


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
    _check_balances(cursor)
    _check_tips(cursor)
    _check_bundles(cursor)


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
    assert conflicting_tips == 0


def _check_balances(cursor):
    """
    Recalculates balances for all participants from transfers and exchanges.

    https://github.com/gratipay/gratipay.com/issues/1118
    """
    b = cursor.all("""
        select p.id, expected, balance as actual
          from (
            select id, sum(a) as expected
              from (
                      select participant as id, sum(amount) as a
                        from exchanges
                       where amount > 0
                         and status = 'succeeded'
                    group by participant

                       union all

                      select participant as id, sum(amount-fee) as a
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
    assert len(b) == 0, "conflicting balances: {}".format(b)


def _check_bundles(cursor):
    """Check that balances and cash bundles are coherent.
    """
    b = cursor.all("""
        SELECT bundles_total, balance
          FROM (
              SELECT owner, sum(amount) AS bundles_total
                FROM cash_bundles b
            GROUP BY owner
          ) foo
          JOIN participants p ON p.id = owner
         WHERE bundles_total <> balance
    """)
    assert len(b) == 0, "bundles are out of whack: {}".format(b)


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
        db.run(sql)
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


def show_table(db, table):
    assert re.match(r'^\w+$', table)
    print('\n{:=^80}'.format(table))
    data = db.all('select * from '+table)
    if len(data) == 0:
        return
    widths = list(len(k) for k in data[0]._fields)
    for row in data:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(str(v)))
    for k, w in zip(data[0]._fields, widths):
        print("{0:{width}}".format(str(k), width=w), end=' | ')
    print()
    for row in data:
        for v, w in zip(row, widths):
            print("{0:{width}}".format(str(v), width=w), end=' | ')
        print()

SimpleCursorBase.show_table = show_table


if __name__ == '__main__':
    from liberapay import wireup
    db = wireup.minimal_algorithm.run()['db']
    print('Checking DB...')
    db.self_check()
    r = run_migrations(db)
    if r:
        print('Checking DB...')
        db.self_check()
