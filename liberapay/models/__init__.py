from contextlib import contextmanager

from postgres import Postgres


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
