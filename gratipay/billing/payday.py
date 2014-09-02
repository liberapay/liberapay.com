"""This is Gratipay's payday algorithm.

Exchanges (moving money between Gratipay and the outside world) and transfers
(moving money amongst Gratipay users) happen within an isolated event called
payday. This event has duration (it's not punctiliar).

Payday is designed to be crash-resistant. Everything that can be rolled back
happens inside a single DB transaction. Exchanges cannot be rolled back, so they
immediately affect the participant's balance.

"""
from __future__ import unicode_literals

import itertools
from multiprocessing.dummy import Pool as ThreadPool

from balanced import CardHold

import aspen.utils
from aspen import log
from gratipay.billing.exchanges import (
    ach_credit, cancel_card_hold, capture_card_hold, create_card_hold, upcharge
)
from gratipay.exceptions import NegativeBalance
from gratipay.models import check_db
from psycopg2 import IntegrityError


with open('fake_payday.sql') as f:
    FAKE_PAYDAY = f.read()


def threaded_map(func, iterable, threads=5):
    pool = ThreadPool(threads)
    r = pool.map(func, iterable)
    pool.close()
    pool.join()
    return r


class NoPayday(Exception):
    __str__ = lambda self: "No payday found where one was expected."


class Payday(object):
    """Represent an abstract event during which money is moved.

    On Payday, we want to use a participant's Gratipay balance to settle their
    tips due (pulling in more money via credit card as needed), but we only
    want to use their balance at the start of Payday. Balance changes should be
    atomic globally per-Payday.

    Here's the call structure of the Payday.run method:

        run
            payin
                prepare
                create_card_holds
                transfer_tips
                transfer_takes
                settle_card_holds
                update_balances
                take_over_balances
            payout
            update_stats
            update_receiving_amounts
            end

    """


    @classmethod
    def start(cls):
        """Try to start a new Payday.

        If there is a Payday that hasn't finished yet, then the UNIQUE
        constraint on ts_end will kick in and notify us of that. In that case
        we load the existing Payday and work on it some more. We use the start
        time of the current Payday to synchronize our work.

        """
        try:
            d = cls.db.one("""
                INSERT INTO paydays DEFAULT VALUES
                RETURNING id, (ts_start AT TIME ZONE 'UTC') AS ts_start, stage
            """, back_as=dict)
            log("Starting a new payday.")
        except IntegrityError:  # Collision, we have a Payday already.
            d = cls.db.one("""
                SELECT id, (ts_start AT TIME ZONE 'UTC') AS ts_start, stage
                  FROM paydays
                 WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
            """, back_as=dict)
            log("Picking up with an existing payday.")

        d['ts_start'] = d['ts_start'].replace(tzinfo=aspen.utils.utc)

        log("Payday started at %s." % d['ts_start'])

        payday = Payday()
        payday.__dict__.update(d)
        return payday


    def run(self):
        """This is the starting point for payday.

        This method runs every Thursday. It is structured such that it can be
        run again safely (with a newly-instantiated Payday object) if it
        crashes.

        """
        self.db.self_check()

        _start = aspen.utils.utcnow()
        log("Greetings, program! It's PAYDAY!!!!")

        if self.stage < 1:
            self.payin()
            self.mark_stage_done()
        if self.stage < 2:
            self.payout()
            self.mark_stage_done()
        if self.stage < 3:
            self.update_stats()
            self.update_receiving_amounts()
            self.mark_stage_done()

        self.end()

        _end = aspen.utils.utcnow()
        _delta = _end - _start
        fmt_past = "Script ran for %%(age)s (%s)." % _delta
        log(aspen.utils.to_age(_start, fmt_past=fmt_past))


    def payin(self):
        """The first stage of payday where we charge credit cards and transfer
        money internally between participants.
        """
        with self.db.get_cursor() as cursor:
            self.prepare(cursor, self.ts_start)
            holds = self.create_card_holds(cursor)
            self.transfer_tips(cursor)
            self.transfer_takes(cursor, self.ts_start)
            transfers = cursor.all("""
                SELECT * FROM transfers WHERE "timestamp" > %s
            """, (self.ts_start,))
            try:
                self.settle_card_holds(cursor, holds)
                self.update_balances(cursor)
                check_db(cursor)
            except:
                # Dump transfers for debugging
                import csv
                from time import time
                with open('%s_transfers.csv' % time(), 'wb') as f:
                    csv.writer(f).writerows(transfers)
                raise
        self.take_over_balances()
        # Clean up leftover functions
        self.db.run("""
            DROP FUNCTION process_take();
            DROP FUNCTION process_tip();
            DROP FUNCTION transfer(text, text, numeric, context_type);
        """)


    @staticmethod
    def prepare(cursor, ts_start):
        """Prepare the DB: we need temporary tables with indexes and triggers.
        """
        cursor.run("""

        -- Create the necessary temporary tables and indexes

        CREATE TEMPORARY TABLE payday_participants ON COMMIT DROP AS
            SELECT id
                 , username
                 , claimed_time
                 , balance AS old_balance
                 , balance AS new_balance
                 , balanced_customer_href
                 , last_bill_result
                 , is_suspicious
                 , goal
                 , false AS card_hold_ok
              FROM participants
             WHERE is_suspicious IS NOT true
               AND claimed_time < %(ts_start)s
          ORDER BY claimed_time;

        CREATE UNIQUE INDEX ON payday_participants (id);
        CREATE UNIQUE INDEX ON payday_participants (username);

        CREATE TEMPORARY TABLE payday_transfers_done ON COMMIT DROP AS
            SELECT *
              FROM transfers t
             WHERE t.timestamp > %(ts_start)s;

        CREATE TEMPORARY TABLE payday_tips ON COMMIT DROP AS
            SELECT tipper, tippee, amount
              FROM ( SELECT DISTINCT ON (tipper, tippee) *
                       FROM tips
                      WHERE mtime < %(ts_start)s
                   ORDER BY tipper, tippee, mtime DESC
                   ) t
              JOIN payday_participants p ON p.username = t.tipper
              JOIN payday_participants p2 ON p2.username = t.tippee
             WHERE t.amount > 0
               AND (p2.goal IS NULL or p2.goal >= 0)
               AND ( SELECT id
                       FROM payday_transfers_done t2
                      WHERE t.tipper = t2.tipper
                        AND t.tippee = t2.tippee
                        AND context = 'tip'
                   ) IS NULL
          ORDER BY p.claimed_time ASC, t.ctime ASC;

        CREATE INDEX ON payday_tips (tipper);
        CREATE INDEX ON payday_tips (tippee);
        ALTER TABLE payday_tips ADD COLUMN is_funded boolean;

        ALTER TABLE payday_participants ADD COLUMN giving_today numeric(35,2);
        UPDATE payday_participants
           SET giving_today = COALESCE((
                   SELECT sum(amount)
                     FROM payday_tips
                    WHERE tipper = username
               ), 0);

        CREATE TEMPORARY TABLE payday_takes
        ( team text
        , member text
        , amount numeric(35,2)
        ) ON COMMIT DROP;

        CREATE TEMPORARY TABLE payday_transfers
        ( timestamp timestamptz DEFAULT now()
        , tipper text
        , tippee text
        , amount numeric(35,2)
        , context context_type
        ) ON COMMIT DROP;


        -- Prepare a statement that makes and records a transfer

        CREATE OR REPLACE FUNCTION transfer(text, text, numeric, context_type)
        RETURNS void AS $$
            BEGIN
                IF ($3 = 0) THEN RETURN; END IF;
                UPDATE payday_participants
                   SET new_balance = (new_balance - $3)
                 WHERE username = $1;
                UPDATE payday_participants
                   SET new_balance = (new_balance + $3)
                 WHERE username = $2;
                INSERT INTO payday_transfers
                            (tipper, tippee, amount, context)
                     VALUES ( ( SELECT p.username
                                  FROM participants p
                                  JOIN payday_participants p2 ON p.id = p2.id
                                 WHERE p2.username = $1 )
                            , ( SELECT p.username
                                  FROM participants p
                                  JOIN payday_participants p2 ON p.id = p2.id
                                 WHERE p2.username = $2 )
                            , $3
                            , $4
                            );
            END;
        $$ LANGUAGE plpgsql;


        -- Create a trigger to process tips

        CREATE OR REPLACE FUNCTION process_tip() RETURNS trigger AS $$
            DECLARE
                tipper payday_participants;
            BEGIN
                tipper := (
                    SELECT p.*::payday_participants
                      FROM payday_participants p
                     WHERE username = NEW.tipper
                );
                IF (NEW.amount <= tipper.new_balance OR tipper.card_hold_ok) THEN
                    EXECUTE transfer(NEW.tipper, NEW.tippee, NEW.amount, 'tip');
                    RETURN NEW;
                END IF;
                RETURN NULL;
            END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER process_tip BEFORE UPDATE OF is_funded ON payday_tips
            FOR EACH ROW
            WHEN (NEW.is_funded IS true AND OLD.is_funded IS NOT true)
            EXECUTE PROCEDURE process_tip();


        -- Create a trigger to process takes

        CREATE OR REPLACE FUNCTION process_take() RETURNS trigger AS $$
            DECLARE
                actual_amount numeric(35,2);
                team_balance numeric(35,2);
            BEGIN
                team_balance := (
                    SELECT new_balance
                      FROM payday_participants
                     WHERE username = NEW.team
                );
                IF (team_balance <= 0) THEN RETURN NULL; END IF;
                actual_amount := NEW.amount;
                IF (team_balance < NEW.amount) THEN
                    actual_amount := team_balance;
                END IF;
                EXECUTE transfer(NEW.team, NEW.member, actual_amount, 'take');
                RETURN NULL;
            END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER process_take AFTER INSERT ON payday_takes
            FOR EACH ROW EXECUTE PROCEDURE process_take();


        -- Save the stats we already have

        UPDATE paydays
           SET nparticipants = (SELECT count(*) FROM payday_participants)
             , ncc_missing = (
                   SELECT count(*)
                     FROM payday_participants
                    WHERE old_balance < giving_today
                      AND ( balanced_customer_href IS NULL
                            OR
                            last_bill_result IS NULL
                          )
               )
         WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz;

        """, dict(ts_start=ts_start))
        log('Prepared the DB.')


    @staticmethod
    def fetch_card_holds(participant_ids):
        holds = {}
        for hold in CardHold.query.filter(CardHold.f.meta.state == 'new'):
            state = 'new'
            if hold.failure_reason:
                state = 'failed'
            elif hold.voided_at:
                state = 'cancelled'
            elif getattr(hold, 'debit_href', None):
                state = 'captured'
            if state != 'new':
                hold.meta['state'] = state
                hold.save()
                continue
            p_id = int(hold.meta['participant_id'])
            if p_id in participant_ids:
                holds[p_id] = hold
            else:
                cancel_card_hold(hold)
        return holds


    def create_card_holds(self, cursor):

        # Get the list of participants to create card holds for
        participants = cursor.all("""
            SELECT *
              FROM payday_participants
             WHERE old_balance < giving_today
               AND balanced_customer_href IS NOT NULL
               AND last_bill_result IS NOT NULL
               AND is_suspicious IS false
        """)
        if not participants:
            return {}

        # Fetch existing holds
        participant_ids = set(p.id for p in participants)
        holds = self.fetch_card_holds(participant_ids)

        # Create new holds and check amounts of existing ones
        def f(p):
            amount = p.giving_today
            if p.old_balance < 0:
                amount -= p.old_balance
            if p.id in holds:
                charge_amount = upcharge(amount)[0]
                if holds[p.id].amount >= charge_amount * 100:
                    return
                else:
                    # The amount is too low, cancel the hold and make a new one
                    cancel_card_hold(holds.pop(p.id))
            hold, error = create_card_hold(self.db, p, amount)
            if error:
                self.mark_charge_failed(cursor)
            else:
                holds[p.id] = hold
        threaded_map(f, participants)

        # Update the values of card_hold_ok in our temporary table
        if not holds:
            return {}
        cursor.run("""
            UPDATE payday_participants p
               SET card_hold_ok = true
             WHERE p.id IN %s
        """, (tuple(holds.keys()),))

        return holds


    @staticmethod
    def transfer_tips(cursor):
        cursor.run("""

        UPDATE payday_tips t
           SET is_funded = true
          FROM payday_participants p
         WHERE p.username = t.tipper
           AND p.card_hold_ok;

        UPDATE payday_tips t
           SET is_funded = true
         WHERE is_funded IS NOT true;

        """)


    @staticmethod
    def transfer_takes(cursor, ts_start):
        cursor.run("""

        INSERT INTO payday_takes
            SELECT team, member, amount
              FROM ( SELECT DISTINCT ON (team, member)
                            team, member, amount, ctime
                       FROM takes
                      WHERE mtime < %(ts_start)s
                   ORDER BY team, member, mtime DESC
                   ) t
             WHERE t.amount > 0
               AND t.team IN (SELECT username FROM payday_participants)
               AND t.member IN (SELECT username FROM payday_participants)
               AND ( SELECT id
                       FROM payday_transfers_done t2
                      WHERE t.team = t2.tipper
                        AND t.member = t2.tippee
                        AND context = 'take'
                   ) IS NULL
          ORDER BY t.team, t.ctime DESC;

        """, dict(ts_start=ts_start))


    def settle_card_holds(self, cursor, holds):
        participants = cursor.all("""
            SELECT *
              FROM payday_participants
             WHERE new_balance < 0
        """)
        participants = [p for p in participants if p.id in holds]

        # Capture holds to bring balances back up to (at least) zero
        def capture(p):
            amount = -p.new_balance
            capture_card_hold(self.db, p, amount, holds.pop(p.id))
        threaded_map(capture, participants)
        log("Captured %i card holds." % len(participants))

        # Cancel the remaining holds
        threaded_map(cancel_card_hold, holds.values())
        log("Canceled %i card holds." % len(holds))


    @staticmethod
    def update_balances(cursor):
        participants = cursor.all("""

            UPDATE participants p
               SET balance = (balance + p2.new_balance - p2.old_balance)
              FROM payday_participants p2
             WHERE p.id = p2.id
               AND p2.new_balance <> p2.old_balance
         RETURNING p.id
                 , p.username
                 , balance AS new_balance
                 , ( SELECT balance
                       FROM participants p3
                      WHERE p3.id = p.id
                   ) AS cur_balance;

        """)
        # Check that balances aren't becoming (more) negative
        for p in participants:
            if p.new_balance < 0 and p.new_balance < p.cur_balance:
                log(p)
                raise NegativeBalance()
        cursor.run("""
            INSERT INTO transfers (timestamp, tipper, tippee, amount, context)
                SELECT * FROM payday_transfers;
        """)
        log("Updated the balances of %i participants." % len(participants))


    def take_over_balances(self):
        """If an account that receives money is taken over during payin we need
        to transfer the balance to the absorbing account.
        """
        for i in itertools.count():
            if i > 10:
                raise Exception('possible infinite loop')
            count = self.db.one("""

                DROP TABLE IF EXISTS temp;
                CREATE TEMPORARY TABLE temp AS
                    SELECT archived_as, absorbed_by, balance AS archived_balance
                      FROM absorptions a
                      JOIN participants p ON a.archived_as = p.username
                     WHERE balance > 0;

                SELECT count(*) FROM temp;

            """)
            if not count:
                break
            self.db.run("""

                INSERT INTO transfers (tipper, tippee, amount, context)
                    SELECT archived_as, absorbed_by, archived_balance, 'take-over'
                      FROM temp;

                UPDATE participants
                   SET balance = (balance - archived_balance)
                  FROM temp
                 WHERE username = archived_as;

                UPDATE participants
                   SET balance = (balance + archived_balance)
                  FROM temp
                 WHERE username = absorbed_by;

            """)


    def payout(self):
        """This is the second stage of payday in which we send money out to the
        bank accounts of participants.
        """
        log("Starting payout loop.")
        participants = self.db.all("""
            SELECT p.*::participants
              FROM participants p
             WHERE balance > 0
               AND balanced_customer_href IS NOT NULL
               AND last_ach_result IS NOT NULL
        """)
        def credit(participant):
            if participant.is_suspicious is None:
                log("UNREVIEWED: %s" % participant.username)
                return
            withhold = participant.giving + participant.pledging
            error = ach_credit(self.db, participant, withhold)
            if error:
                self.mark_ach_failed()
        threaded_map(credit, participants)
        log("Did payout for %d participants." % len(participants))
        self.db.self_check()
        log("Checked the DB.")


    def update_stats(self):
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
                 , ntippers = (SELECT count(DISTINCT tipper) FROM our_transfers)
                 , ntips = (SELECT count(*) FROM our_tips)
                 , npachinko = (SELECT count(*) FROM our_pachinkos)
                 , pachinko_volume = (SELECT COALESCE(sum(amount), 0) FROM our_pachinkos)
                 , ntransfers = (SELECT count(*) FROM our_transfers)
                 , transfer_volume = (SELECT COALESCE(sum(amount), 0) FROM our_transfers)
                 , nachs = (SELECT count(*) FROM our_achs)
                 , ach_volume = (SELECT COALESCE(sum(amount), 0) FROM our_achs)
                 , ach_fees_volume = (SELECT COALESCE(sum(fee), 0) FROM our_achs)
                 , ncharges = (SELECT count(*) FROM our_charges)
                 , charge_volume = (
                       SELECT COALESCE(sum(amount + fee), 0)
                         FROM our_charges
                   )
                 , charge_fees_volume = (SELECT COALESCE(sum(fee), 0) FROM our_charges)
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz

        """, {'ts_start': self.ts_start})
        log("Updated payday stats.")


    def update_receiving_amounts(self):
        with self.db.get_cursor() as cursor:
            cursor.execute(FAKE_PAYDAY)
        log("Updated receiving amounts.")


    def end(self):
        self.ts_end = self.db.one("""\

            UPDATE paydays
               SET ts_end=now()
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING ts_end AT TIME ZONE 'UTC'

        """, default=NoPayday).replace(tzinfo=aspen.utils.utc)


    # Record-keeping.
    # ===============

    @staticmethod
    def mark_charge_failed(cursor):
        cursor.one("""\

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


    def mark_stage_done(self):
        self.db.one("""\

            UPDATE paydays
               SET stage = stage + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)
