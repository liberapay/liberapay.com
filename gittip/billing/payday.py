"""This is Gittip's payday algorithm. I would appreciate feedback on it.

The payday algorithm is designed to be crash-resistant and parallelizable, but
it's not eventually consistent in the strict sense (iinm) because consistency
is always apodeictically knowable.

Exchanges (moving money between Gittip and the outside world) and transfers
(moving money amongst Gittip users) happen within an isolated event called
payday. This event has duration (it's not punctiliar). It is started
transactionally, and it ends transactionally, and inside of it, exchanges and
transfers happen transactionally (though the link between our db and our
processor's db could be tightened up; see #213). Exchanges immediately affect
the participant's balance, but transfers accrue against a "pending" column in
the database. Once the payday event has completed successfully, it ends with
the pending column being applied to the balance column and reset to NULL in a
single transaction.

"""
from __future__ import unicode_literals

from decimal import Decimal

import aspen.utils
from aspen import log
from aspen.utils import typecheck
from gittip.billing.exchanges import ach_credit, charge
from gittip.exceptions import NegativeBalance, NoBalancedCustomerHref, NotWhitelisted
from psycopg2 import IntegrityError


class NoPayday(Exception):
    def __str__(self):
        return "No payday found where one was expected."


class Payday(object):
    """Represent an abstract event during which money is moved.

    On Payday, we want to use a participant's Gittip balance to settle their
    tips due (pulling in more money via credit card as needed), but we only
    want to use their balance at the start of Payday. Balance changes should be
    atomic globally per-Payday.

    """

    def __init__(self, db):
        """Takes a postgres.Postgres instance.
        """
        self.db = db


    def run(self):
        """This is the starting point for payday.

        This method runs every Thursday. It is structured such that it can be
        run again safely (with a newly-instantiated Payday object) if it
        crashes.

        """
        self.db.self_check()

        _start = aspen.utils.utcnow()
        log("Greetings, program! It's PAYDAY!!!!")
        ts_start = self.start()
        self.prepare(ts_start)
        self.zero_out_pending(ts_start)

        self.payin()
        self.move_pending_to_balance_for_teams()
        self.pachinko()
        self.clear_pending_to_balance()
        self.payout()
        self.update_stats(ts_start)
        self.update_receiving_amounts()

        self.end()

        self.db.self_check()

        _end = aspen.utils.utcnow()
        _delta = _end - _start
        fmt_past = "Script ran for {age} (%s)." % _delta
        log(aspen.utils.to_age(_start, fmt_past=fmt_past))


    def start(self):
        """Try to start a new Payday.

        If there is a Payday that hasn't finished yet, then the UNIQUE
        constraint on ts_end will kick in and notify us of that. In that case
        we load the existing Payday and work on it some more. We use the start
        time of the current Payday to synchronize our work.

        """
        try:
            ts_start = self.db.one("INSERT INTO paydays DEFAULT VALUES "
                                   "RETURNING ts_start")
            log("Starting a new payday.")
        except IntegrityError:  # Collision, we have a Payday already.
            ts_start = self.db.one("""

                SELECT ts_start
                  FROM paydays
                 WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz

            """)
            log("Picking up with an existing payday.")

        log("Payday started at %s." % ts_start)
        return ts_start


    def prepare(self, ts_start):
        """Prepare the DB: we need temporary tables with indexes.
        """
        self.db.run("""

        DROP TABLE IF EXISTS pay_participants CASCADE;
        CREATE TEMPORARY TABLE pay_participants AS
            SELECT username
                 , claimed_time
                 , number
                 , is_suspicious
                 , balance
                 , balanced_customer_href
                 , last_bill_result
              FROM participants
             WHERE is_suspicious IS NOT true
               AND claimed_time < %(ts_start)s
          ORDER BY claimed_time;

        CREATE UNIQUE INDEX ON pay_participants (username);

        DROP TABLE IF EXISTS pay_transfers CASCADE;
        CREATE TEMPORARY TABLE pay_transfers AS
            SELECT *
              FROM transfers t
             WHERE t.timestamp > %(ts_start)s;

        DROP TABLE IF EXISTS pay_tips CASCADE;
        CREATE TEMPORARY TABLE pay_tips AS
            SELECT tipper, tippee, amount
              FROM ( SELECT DISTINCT ON (tipper, tippee) *
                       FROM tips
                      WHERE mtime < %(ts_start)s
                   ORDER BY tipper, tippee, mtime DESC
                   ) t
              JOIN pay_participants p ON p.username = t.tipper
             WHERE t.amount > 0
               AND t.tippee IN (SELECT username FROM pay_participants)
               AND ( SELECT id
                       FROM pay_transfers t2
                      WHERE t.tipper = t2.tipper
                        AND t.tippee = t2.tippee
                        AND context = 'tip'
                   ) IS NULL
          ORDER BY p.claimed_time ASC, t.ctime ASC;

        CREATE INDEX ON pay_tips (tipper);
        CREATE INDEX ON pay_tips (tippee);

        ALTER TABLE pay_participants ADD COLUMN giving_today numeric(35,2);
        UPDATE pay_participants
           SET giving_today = (
                   SELECT sum(amount)
                     FROM pay_tips
                    WHERE tipper = username
               );

        DROP TABLE IF EXISTS pay_takes CASCADE;
        CREATE TEMPORARY TABLE pay_takes AS
            SELECT team, member, amount, ctime
              FROM ( SELECT DISTINCT ON (team, member)
                            team, member, amount, ctime
                       FROM takes
                      WHERE mtime < %(ts_start)s
                   ORDER BY team, member, mtime DESC
                   ) t
             WHERE t.amount > 0
               AND t.team IN (SELECT username FROM pay_participants)
               AND t.member IN (SELECT username FROM pay_participants)
               AND ( SELECT id
                       FROM pay_transfers t2
                      WHERE t.team = t2.tipper
                        AND t.member = t2.tippee
                        AND context = 'take'
                   ) IS NULL;

        CREATE INDEX ON pay_takes (team);

        """, dict(ts_start=ts_start))
        log('Prepared the DB.')


    def zero_out_pending(self, ts_start):
        """Given a timestamp, zero out the pending column.

        We keep track of balance changes as a result of Payday in the pending
        column, and then move them over to the balance column in one big
        transaction at the end of Payday.

        """
        START_PENDING = """\

            UPDATE participants
               SET pending=0.00
             WHERE pending IS NULL
               AND claimed_time < %s

        """
        self.db.run(START_PENDING, (ts_start,))
        log("Zeroed out the pending column.")
        return None


    def payin(self):
        """Do the payin side of Payday.
        """
        i = 0
        log("Starting payin loop.")
        participants = self.db.all("""
            SELECT * FROM pay_participants WHERE giving_today > 0
        """)
        for i, participant in enumerate(participants, start=1):
            if i % 100 == 0:
                log("Payin done for %d participants." % i)
            self.charge_and_or_transfer(participant)
        log("Did payin for %d participants." % i)


    def pachinko(self):
        i = 0
        participants = self.db.all("""
            SELECT * FROM pay_participants WHERE number = 'plural'
        """)
        for i, participant in enumerate(participants, start=1):
            if i % 100 == 0:
                log("Pachinko done for %d participants." % i)

            available = participant.balance
            log("Pachinko out from %s with $%s." % ( participant.username
                                                   , available
                                                    ))

            def tip(tippee, amount):
                tip = {}
                tip['tipper'] = participant.username
                tip['tippee'] = tippee
                tip['amount'] = amount
                self.tip( participant
                        , tip
                        , pachinko=True
                         )

            takes = self.db.all("""
                SELECT * FROM pay_takes WHERE team = %s ORDER BY ctime DESC
            """, (participant.username,), back_as=dict)

            for take in takes:
                amount = min(take['amount'], available)
                available -= amount
                tip(take['member'], amount)
                if available == 0:
                    break

        log("Did pachinko for %d participants." % i)


    def payout(self):
        """Do the payout side of Payday.
        """
        i = 0
        log("Starting payout loop.")
        participants = self.db.all("""
            SELECT p.*::participants FROM participants p WHERE balance > 0
        """)
        for i, participant in enumerate(participants, start=1):
            if i % 100 == 0:
                log("Payout done for %d participants." % i)
            withhold = participant.giving + participant.pledging
            try:
                error = ach_credit(self.db, participant, withhold)
                if error:
                    self.mark_ach_failed()
            except NoBalancedCustomerHref:
                continue
            except NotWhitelisted:
                if participant.is_suspicious is None:
                    log("UNREVIEWED: %s" % participant.username)
        log("Did payout for %d participants." % i)


    def charge_and_or_transfer(self, participant):
        """Given one participant record, pay their day.

        Charge each participants' credit card if needed before transfering
        money between Gittip accounts.

        """
        short = participant.giving_today - participant.balance
        if short > 0:

            # The participant's Gittip account is short the amount needed to
            # fund all their tips. Let's try pulling in money from their credit
            # card. If their credit card fails we'll forge ahead, in case they
            # have a positive Gittip balance already that can be used to fund
            # at least *some* tips. The charge method will have set
            # last_bill_result to a non-empty string if the card did fail.

            try:
                error = charge(self.db, participant, short)
                if error:
                    self.mark_charge_failed()
            except NoBalancedCustomerHref:
                self.mark_missing_funding()
            except NotWhitelisted:
                if participant.is_suspicious is None:
                    log("UNREVIEWED: %s" % participant.username)

        tips = self.db.all("""
            SELECT * FROM pay_tips WHERE tipper = %s
        """, (participant.username,), back_as=dict)

        nsuccessful_tips = 0
        for tip in tips:
            result = self.tip(participant, tip)
            if result >= 0:
                nsuccessful_tips += result
            else:
                break


    def move_pending_to_balance_for_teams(self):
        """Transfer pending into balance for teams.

        We do this because debit_participant operates against balance, not
        pending. This is because credit card charges go directly into balance
        on the first (payin) loop.

        """
        self.db.run("""\

            UPDATE participants
               SET balance = (balance + pending)
                 , pending = 0
             WHERE pending IS NOT NULL
               AND number='plural'

        """)
        # "Moved" instead of "cleared" because we don't also set to null.
        log("Moved pending to balance for teams. Ready for pachinko.")


    def clear_pending_to_balance(self):
        """Transfer pending into balance, setting pending to NULL.

        Any users that were created while the payin loop was running will have
        pending NULL (the default). If we try to add that to balance we'll get
        a NULL (0.0 + NULL = NULL), and balance has a NOT NULL constraint.
        Hence the where clause. See:

            https://github.com/gittip/www.gittip.com/issues/170

        """

        self.db.run("""\

            UPDATE participants
               SET balance = (balance + pending)
                 , pending = NULL
             WHERE pending IS NOT NULL

        """)
        # "Cleared" instead of "moved because we also set to null.
        log("Cleared pending to balance. Ready for payouts.")


    def update_stats(self, ts_start):
        self.db.run("""\

            WITH our_transfers AS (
                     SELECT *
                       FROM transfers
                      WHERE "timestamp" >= %(ts_start)s
                 )
               , our_tips AS (
                     SELECT *
                       FROM our_transfers
                      WHERE context = 'tip'
                 )
               , our_pachinkos AS (
                     SELECT *
                       FROM our_transfers
                      WHERE context = 'take'
                 )
               , our_exchanges AS (
                     SELECT *
                       FROM exchanges
                      WHERE "timestamp" >= %(ts_start)s
                 )
               , our_achs AS (
                     SELECT *
                       FROM our_exchanges
                      WHERE amount < 0
                 )
               , our_charges AS (
                     SELECT *
                       FROM our_exchanges
                      WHERE amount > 0
                 )
            UPDATE paydays
               SET nactive = (
                       SELECT DISTINCT count(*) FROM (
                           SELECT tipper FROM our_transfers
                               UNION
                           SELECT tippee FROM our_transfers
                       ) AS foo
                   )
                 , nparticipants = (SELECT count(*) FROM pay_participants)
                 , ntippers = (SELECT count(DISTINCT tipper) FROM our_transfers)
                 , ntips = (SELECT count(*) FROM our_tips)
                 , npachinko = (SELECT count(*) FROM our_pachinkos)
                 , pachinko_volume = (SELECT sum(amount) FROM our_pachinkos)
                 , ntransfers = (SELECT count(*) FROM our_transfers)
                 , transfer_volume = (SELECT sum(amount) FROM our_transfers)
                 , nachs = (SELECT count(*) FROM our_achs)
                 , ach_volume = (SELECT COALESCE(sum(amount), 0) FROM our_achs)
                 , ach_fees_volume = (SELECT sum(fee) FROM our_achs)
                 , ncharges = (SELECT count(*) FROM our_charges)
                 , charge_volume = (
                       SELECT COALESCE(sum(amount + fee), 0)
                         FROM our_charges
                   )
                 , charge_fees_volume = (SELECT sum(fee) FROM our_charges)
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz

        """, {'ts_start': ts_start})


    def update_receiving_amounts(self):
        UPDATE = """
            CREATE OR REPLACE TEMPORARY VIEW total_receiving AS
                SELECT tippee, sum(amount) AS amount, count(*) AS ntippers
                  FROM current_tips
                  JOIN participants p ON p.username = tipper
                 WHERE p.is_suspicious IS NOT TRUE
                   AND p.last_bill_result = ''
                   AND amount > 0
              GROUP BY tippee;

            UPDATE participants
               SET receiving = (amount + taking)
                 , npatrons = ntippers
              FROM total_receiving
             WHERE tippee = username;
        """
        with self.db.get_cursor() as cursor:
            cursor.execute(UPDATE)

    def end(self):
        self.db.one("""\

            UPDATE paydays
               SET ts_end=now()
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)


    # Move money between Gittip participants.
    # =======================================

    def tip(self, participant, tip, pachinko=False):
        """Given dict, dict, and datetime, log and return int.

        Return values:

            | 0 if no valid tip available or tip has not been claimed
            | 1 if tip is valid
            | -1 if transfer fails and we cannot continue

        """
        msg = "$%s from %s to %s%s."
        msg %= ( tip['amount']
               , participant.username
               , tip['tippee']
               , " (pachinko)" if pachinko else ""
                )

        if tip['amount'] == 0:

            # The tips table contains a record for every time you click a tip
            # button. So if you click $0.25 then $3.00 then $0.00, that
            # generates three entries. We are looking at the last entry here,
            # and it's zero.

            return 0

        if not self.transfer(participant.username, tip['tippee'], \
                                             tip['amount'], pachinko=pachinko):

            # The transfer failed due to a lack of funds for the participant.
            # Don't try any further transfers.

            log("FAILURE: %s" % msg)
            return -1

        log("SUCCESS: %s" % msg)
        return 1


    def transfer(self, tipper, tippee, amount, pachinko=False):
        """Given two unicodes, a Decimal, and a boolean, return a boolean.

        If the tipper doesn't have enough in their Gittip account then we
        return False. Otherwise we decrement tipper's balance and increment
        tippee's *pending* balance by amount.

        """
        typecheck( tipper, unicode
                 , tippee, unicode
                 , amount, Decimal
                 , pachinko, bool
                  )
        with self.db.get_cursor() as cursor:

            try:
                self.debit_participant(cursor, tipper, amount)
            except NegativeBalance:
                return False

            self.credit_participant(cursor, tippee, amount)
            context = 'take' if pachinko else 'tip'
            self.record_transfer(cursor, tipper, tippee, amount, context)

            return True


    def debit_participant(self, cursor, participant, amount):
        """Decrement the tipper's balance.
        """

        DECREMENT = """\

           UPDATE participants
              SET balance = (balance - %(amount)s)
            WHERE username = %(participant)s
              AND balance >= %(amount)s
        RETURNING pending

        """
        args = dict(amount=amount, participant=participant)
        r = cursor.one(DECREMENT, args, default=False)
        if r is False:
            raise NegativeBalance
        assert r is not None, (amount, participant)  # sanity check


    def credit_participant(self, cursor, participant, amount):
        """Increment the tippee's *pending* balance.

        The pending balance will clear to the balance proper when Payday is
        done.

        """

        INCREMENT = """\

           UPDATE participants
              SET pending=(pending + %s)
            WHERE username=%s
              AND pending IS NOT NULL
        RETURNING pending

        """
        cursor.execute(INCREMENT, (amount, participant))
        rec = cursor.fetchone()
        assert rec is not None, (participant, amount)  # sanity check


    # Record-keeping.
    # ===============

    def record_transfer(self, cursor, tipper, tippee, amount, context):
        cursor.run("""\

          INSERT INTO transfers
                      (tipper, tippee, amount, context)
               VALUES (%s, %s, %s, %s)

        """, (tipper, tippee, amount, context))


    def mark_missing_funding(self):
        self.db.one("""\

            UPDATE paydays
               SET ncc_missing = ncc_missing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)


    def mark_charge_failed(self):
        self.db.one("""\

            UPDATE paydays
               SET ncc_failing = ncc_failing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)


    def mark_ach_failed(self):
        self.db.one("""\

            UPDATE paydays
               SET nach_failing = nach_failing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)
