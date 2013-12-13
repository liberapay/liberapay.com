"""

The most important object in the Gittip object model is Participant, and the
second most important one is Ccommunity. There are a few others, but those are
the most important two. Participant, in particular, is at the center of
everything on Gittip.

"""
from postgres import Postgres

class GittipDB(Postgres):

    def self_check(self):
        """
        Runs all available self checks on the database.
        """
        self._check_balances()
        self._check_tips()
        self._check_orphans()

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
        b = self.one("""
            select count(*)
              from (
                select username, sum(a) as balance
                  from (
                          select participant as username, sum(amount) as a
                            from exchanges
                           where amount > 0
                        group by participant

                           union

                          select participant as username, sum(amount-fee) as a
                            from exchanges
                           where amount < 0
                        group by participant

                           union

                          select tipper as username, sum(-amount) as a
                            from transfers
                        group by tipper

                           union

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
        e = self.one("""
            select count((username, ctime, claimed_time))
               from participants
              where not exists (select * from elsewhere where elsewhere.participant=username)
                and not exists (select * from absorptions where archived_as=username)
        """)
        assert e == 0, "missing elsewheres: {}".format(e)
