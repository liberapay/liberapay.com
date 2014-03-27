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
        """
        Runs all available self checks on the database.
        """
        self._check_balances()
        self._check_tips()
        self._check_orphans()
        self._check_orphans_no_tips()
        self._check_paydays_volumes()
        self._check_claimed_not_locked()

    def _check_tips(self):
        """
        Checks that there are no rows in tips with duplicate (tipper, tippee, mtime).

        https://github.com/gittip/www.gittip.com/issues/1704
        """
        conflicting_tips = self.one("""
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

    def _check_balances(self):
        """
        Recalculates balances for all participants from transfers and exchanges.

        https://github.com/gittip/www.gittip.com/issues/1118
        """
        with self.get_cursor() as cursor:
            if cursor.one("select exists (select * from paydays where ts_end < ts_start) as running"):
                # payday is running and the query bellow does not account for pending
                return
            b = cursor.one("""
                select count(*)
                  from (
                    select username, sum(a) as balance
                      from (
                              select participant as username, sum(amount) as a
                                from exchanges
                               where amount > 0
                            group by participant

                               union all

                              select participant as username, sum(amount-fee) as a
                                from exchanges
                               where amount < 0
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

                    except

                    select username, balance
                    from participants
                  ) as foo2
            """)
        assert b == 0, "conflicting balances: {}".format(b)

    def _check_orphans(self):
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
        orphans = self.all("""
            select username
               from participants
              where not exists (select * from elsewhere where elsewhere.participant=username)
                and not exists (select * from absorptions where archived_as=username)
        """)
        assert len(orphans) == 0, "missing elsewheres: {}".format(list(orphans))

    def _check_orphans_no_tips(self):
        """
        Finds participants
            * without elsewhere account attached
            * having non zero outstanding tip

        This should not happen because when we remove the last elsewhere account
        in take_over we also zero out all tips.
        """
        tips_with_orphans = self.all("""
            WITH orphans AS (
                SELECT username FROM participants
                WHERE NOT EXISTS (SELECT 1 FROM elsewhere WHERE participant=username)
            ), valid_tips AS (
                  SELECT * FROM (
                            SELECT DISTINCT ON (tipper, tippee) *
                              FROM tips
                          ORDER BY tipper, tippee, mtime DESC
                      ) AS foo
                  WHERE amount > 0
            )
            SELECT id FROM valid_tips
            WHERE tipper IN (SELECT * FROM orphans)
            OR tippee IN (SELECT * FROM orphans)
        """)
        known = set([25206, 46266]) # '4c074000c7bc', 'naderman', '3.00'
        real = set(tips_with_orphans) - known
        assert len(real) == 0, real

    def _check_paydays_volumes(self):
        """
        Recalculate *_volume fields in paydays table using exchanges table.
        """
        with self.get_cursor() as cursor:
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
                        ) as ref
                    from paydays
                    order by id
                ) as foo
                where ach_fees_volume != ref
            """)
            assert len(ach_fees_volume) == 0

    def _check_claimed_not_locked(self):
        locked = self.all("""
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
