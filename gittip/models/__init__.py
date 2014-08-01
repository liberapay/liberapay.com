"""

The most important object in the Gittip object model is Participant, and the
second most important one is Ccommunity. There are a few others, but those are
the most important two. Participant, in particular, is at the center of
everything on Gittip.

"""
from postgres import Postgres
import psycopg2.extras


class GittipDB(Postgres):

    def self_check(self):
        with self.get_cursor() as cursor:
            check_db(cursor)


def check_db(cursor):
    """Runs all available self checks on the given cursor.
    """
    _check_balances(cursor)
    _check_tips(cursor)
    _check_orphans(cursor)
    _check_orphans_no_tips(cursor)
    _check_paydays_volumes(cursor)
    _check_claimed_not_locked(cursor)


def _check_tips(cursor):
    """
    Checks that there are no rows in tips with duplicate (tipper, tippee, mtime).

    https://github.com/gittip/www.gittip.com/issues/1704
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

    https://github.com/gittip/www.gittip.com/issues/1118
    """
    b = cursor.all("""
        select p.username, expected, balance as actual
          from (
            select username, sum(a) as expected
              from (
                      select participant as username, sum(amount) as a
                        from exchanges
                       where amount > 0
                         and (status is null or status = 'succeeded')
                    group by participant

                       union all

                      select participant as username, sum(amount-fee) as a
                        from exchanges
                       where amount < 0
                         and (status is null or status <> 'failed')
                    group by participant

                       union all

                      select tipper as username, sum(-amount) as a
                        from transfers
                    group by tipper

                       union all

                      select tippee as username, sum(amount) as a
                        from transfers
                    group by tippee
                    ) as foo
            group by username
          ) as foo2
        join participants p on p.username = foo2.username
        where expected <> p.balance
    """)
    assert len(b) == 0, "conflicting balances: {}".format(b)


def _check_orphans(cursor):
    """
    Finds participants that
        * does not have corresponding elsewhere account
        * have not been absorbed by other participant

    These are broken because new participants arise from elsewhere
    and elsewhere is detached only by take over which makes a note
    in absorptions if it removes the last elsewhere account.

    Especially bad case is when also claimed_time is set because
    there must have been elsewhere account attached and used to sign in.

    https://github.com/gittip/www.gittip.com/issues/617
    """
    orphans = cursor.all("""
        select username
           from participants
          where not exists (select * from elsewhere where elsewhere.participant=username)
            and not exists (select * from absorptions where archived_as=username)
    """)
    assert len(orphans) == 0, "missing elsewheres: {}".format(list(orphans))


def _check_orphans_no_tips(cursor):
    """
    Finds participants
        * without elsewhere account attached
        * having non zero outstanding tip

    This should not happen because when we remove the last elsewhere account
    in take_over we also zero out all tips.
    """
    orphans_with_tips = cursor.all("""
        WITH valid_tips AS (SELECT * FROM current_tips WHERE amount > 0)
        SELECT username
          FROM (SELECT tipper AS username FROM valid_tips
                UNION
                SELECT tippee AS username FROM valid_tips) foo
         WHERE NOT EXISTS (SELECT 1 FROM elsewhere WHERE participant=username)
    """)
    assert len(orphans_with_tips) == 0, orphans_with_tips


def _check_paydays_volumes(cursor):
    """
    Recalculate *_volume fields in paydays table using exchanges table.
    """
    if cursor.one("select exists (select * from paydays where ts_end < ts_start) as running"):
        # payday is running
        return
    charge_volume = cursor.all("""
        select * from (
            select id, ts_start, charge_volume, (
                    select coalesce(sum(amount+fee), 0)
                    from exchanges
                    where timestamp > ts_start
                    and timestamp < ts_end
                    and amount > 0
                    and recorder is null
                ) as ref
            from paydays
            order by id
        ) as foo
        where charge_volume != ref
    """)
    assert len(charge_volume) == 0

    charge_fees_volume = cursor.all("""
        select * from (
            select id, ts_start, charge_fees_volume, (
                    select coalesce(sum(fee), 0)
                    from exchanges
                    where timestamp > ts_start
                    and timestamp < ts_end
                    and amount > 0
                    and recorder is null
                ) as ref
            from paydays
            order by id
        ) as foo
        where charge_fees_volume != ref
    """)
    assert len(charge_fees_volume) == 0

    ach_volume = cursor.all("""
        select * from (
            select id, ts_start, ach_volume, (
                    select coalesce(sum(amount), 0)
                    from exchanges
                    where timestamp > ts_start
                    and timestamp < ts_end
                    and amount < 0
                    and recorder is null
                ) as ref
            from paydays
            order by id
        ) as foo
        where ach_volume != ref
    """)
    assert len(ach_volume) == 0

    ach_fees_volume = cursor.all("""
        select * from (
            select id, ts_start, ach_fees_volume, (
                    select coalesce(sum(fee), 0)
                    from exchanges
                    where timestamp > ts_start
                    and timestamp < ts_end
                    and amount < 0
                    and recorder is null
                ) as ref
            from paydays
            order by id
        ) as foo
        where ach_fees_volume != ref
    """)
    assert len(ach_fees_volume) == 0


def _check_claimed_not_locked(cursor):
    locked = cursor.all("""
        SELECT participant
        FROM elsewhere
        WHERE EXISTS (
            SELECT *
            FROM participants
            WHERE username=participant
            AND claimed_time IS NOT NULL
        ) AND is_locked
    """)
    assert len(locked) == 0


def add_event(c, type, payload):
    SQL = """
        INSERT INTO events (type, payload)
        VALUES (%s, %s)
    """
    c.run(SQL, (type, psycopg2.extras.Json(payload)))
