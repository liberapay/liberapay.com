from __future__ import unicode_literals

import os
import os.path
import pickle

import aspen.utils
from aspen import log
from psycopg2 import IntegrityError

from liberapay import constants
from liberapay.billing.exchanges import transfer
from liberapay.exceptions import NegativeBalance
from liberapay.models.participant import Participant
from liberapay.utils import group_by


class NoPayday(Exception):
    __str__ = lambda self: "No payday found where one was expected."


class NS(object):
    def __init__(self, d):
        self.__dict__.update(d)


class Payday(object):

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
                RETURNING id, (ts_start AT TIME ZONE 'UTC') AS ts_start
            """, back_as=dict)
            log("Starting a new payday.")
        except IntegrityError:  # Collision, we have a Payday already.
            d = cls.db.one("""
                SELECT id, (ts_start AT TIME ZONE 'UTC') AS ts_start
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

        It is structured such that it can be run again safely (with a
        newly-instantiated Payday object) if it crashes.

        """
        self.db.self_check()

        _start = aspen.utils.utcnow()
        log("Greetings, program! It's PAYDAY!!!!")

        self.shuffle()

        self.update_stats()
        self.update_cached_amounts()

        self.end()
        self.notify_participants()

        os.unlink(self.transfers_filename)

        _end = aspen.utils.utcnow()
        _delta = _end - _start
        fmt_past = "Script ran for %%(age)s (%s)." % _delta
        log(aspen.utils.to_age(_start, fmt_past=fmt_past))

    def shuffle(self):
        self.transfers_filename = 'payday-%s_transfers.pickle' % self.id
        if os.path.exists(self.transfers_filename):
            with open(self.transfers_filename, 'rb') as f:
                transfers = pickle.load(f)
            done = self.db.all("""
                SELECT *
                  FROM transfers t
                 WHERE t.timestamp >= %(ts_start)s;
            """, dict(ts_start=self.ts_start))
            done = set((t.tipper, t.tippee, t.context, t.team) for t in done)
            transfers = [t for t in transfers if (t.tipper, t.tippee, t.context, t.team) not in done]
        else:
            with self.db.get_cursor() as cursor:
                self.prepare(cursor, self.ts_start)
                self.transfer_virtually(cursor)
                transfers = [NS(t._asdict()) for t in cursor.all("""
                    SELECT t.*
                         , p.mangopay_user_id AS tipper_mango_id
                         , p2.mangopay_user_id AS tippee_mango_id
                         , p.mangopay_wallet_id AS tipper_wallet_id
                         , p2.mangopay_wallet_id AS tippee_wallet_id
                      FROM payday_transfers t
                      JOIN participants p ON p.id = t.tipper
                      JOIN participants p2 ON p2.id = t.tippee
                """)]
                self.check_balances(cursor)
                with open(self.transfers_filename, 'wb') as f:
                    pickle.dump(transfers, f)
                cursor.run("""
                    UPDATE paydays
                       SET nparticipants = (SELECT count(*) FROM payday_participants)
                     WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz;
                """)
            self.clean_up()

        self.transfer_for_real(transfers)

        self.db.self_check()

    @staticmethod
    def prepare(cursor, ts_start):
        """Prepare the DB: we need temporary tables with indexes and triggers.
        """
        cursor.run("""

        -- Create the necessary temporary tables and indexes

        CREATE TEMPORARY TABLE payday_participants ON COMMIT DROP AS
            SELECT id
                 , username
                 , join_time
                 , balance AS old_balance
                 , balance AS new_balance
                 , is_suspicious
                 , goal
                 , kind
              FROM participants p
             WHERE is_suspicious IS NOT true
               AND join_time < %(ts_start)s
               AND (mangopay_user_id IS NOT NULL OR kind = 'group')
          ORDER BY join_time;

        CREATE UNIQUE INDEX ON payday_participants (id);

        CREATE TEMPORARY TABLE payday_tips ON COMMIT DROP AS
            SELECT t.id, tipper, tippee, amount, (p2.kind = 'group') AS to_team
              FROM ( SELECT DISTINCT ON (tipper, tippee) *
                       FROM tips
                      WHERE mtime < %(ts_start)s
                   ORDER BY tipper, tippee, mtime DESC
                   ) t
              JOIN payday_participants p ON p.id = t.tipper
              JOIN payday_participants p2 ON p2.id = t.tippee
             WHERE t.amount > 0
               AND (p2.goal IS NULL or p2.goal >= 0)
          ORDER BY p.join_time ASC, t.ctime ASC;

        CREATE INDEX ON payday_tips (tipper);
        CREATE INDEX ON payday_tips (tippee);
        ALTER TABLE payday_tips ADD COLUMN is_funded boolean;

        CREATE TEMPORARY TABLE payday_takes ON COMMIT DROP AS
            SELECT team, member, amount
              FROM ( SELECT DISTINCT ON (team, member)
                            team, member, amount
                       FROM takes
                      WHERE mtime < %(ts_start)s
                   ORDER BY team, member, mtime DESC
                   ) t
             WHERE t.amount IS NOT NULL
               AND t.amount > 0
               AND t.team IN (SELECT id FROM payday_participants)
               AND t.member IN (SELECT id FROM payday_participants);

        CREATE UNIQUE INDEX ON payday_takes (team, member);

        CREATE TEMPORARY TABLE payday_transfers
        ( timestamp timestamptz DEFAULT now()
        , tipper bigint
        , tippee bigint
        , amount numeric(35,2)
        , context transfer_context
        , team bigint
        , UNIQUE (tipper, tippee, context, team)
        ) ON COMMIT DROP;


        -- Prepare a statement that makes and records a transfer

        CREATE OR REPLACE FUNCTION transfer(bigint, bigint, numeric, transfer_context, bigint)
        RETURNS void AS $$
            BEGIN
                IF ($3 = 0) THEN RETURN; END IF;
                UPDATE payday_participants
                   SET new_balance = (new_balance - $3)
                 WHERE id = $1;
                IF (NOT FOUND) THEN RAISE 'tipper not found'; END IF;
                UPDATE payday_participants
                   SET new_balance = (new_balance + $3)
                 WHERE id = $2;
                IF (NOT FOUND) THEN RAISE 'tippee not found'; END IF;
                INSERT INTO payday_transfers
                            (tipper, tippee, amount, context, team)
                     VALUES ($1, $2, $3, $4, $5);
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
                     WHERE id = NEW.tipper
                );
                IF (NEW.amount <= tipper.new_balance) THEN
                    EXECUTE transfer(NEW.tipper, NEW.tippee, NEW.amount, 'tip', NULL);
                    RETURN NEW;
                END IF;
                RETURN NULL;
            END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER process_tip BEFORE UPDATE OF is_funded ON payday_tips
            FOR EACH ROW
            WHEN (NEW.is_funded IS true AND OLD.is_funded IS NOT true AND NEW.to_team IS NOT true)
            EXECUTE PROCEDURE process_tip();


        -- Create a function to settle one-to-one donations

        CREATE OR REPLACE FUNCTION settle_tip_graph() RETURNS void AS $$
            DECLARE
                count integer NOT NULL DEFAULT 0;
                i integer := 0;
            BEGIN
                LOOP
                    i := i + 1;
                    WITH updated_rows AS (
                         UPDATE payday_tips
                            SET is_funded = true
                          WHERE is_funded IS NOT true
                            AND to_team IS NOT true
                      RETURNING *
                    )
                    SELECT COUNT(*) FROM updated_rows INTO count;
                    IF (count = 0) THEN
                        EXIT;
                    END IF;
                    IF (i > 50) THEN
                        RAISE 'Reached the maximum number of iterations';
                    END IF;
                END LOOP;
            END;
        $$ LANGUAGE plpgsql;


        -- Create a function to resolve many-to-many donations (team takes)

        CREATE OR REPLACE FUNCTION resolve_takes(team_id bigint) RETURNS void AS $$
            DECLARE
                total_income numeric(35,2);
                total_takes numeric(35,2);
                ratio numeric;
                tip record;
                take record;
                amount numeric(35,2);
                our_tips CURSOR FOR
                    SELECT t.id, t.tipper, (round_up(t.amount * ratio, 2)) AS amount
                      FROM payday_tips t
                      JOIN payday_participants p ON p.id = t.tipper
                     WHERE t.tippee = team_id;
                our_takes CURSOR FOR
                    SELECT t.member, (round_up(t.amount * ratio, 2)) AS amount
                      FROM payday_takes t
                     WHERE t.team = team_id
                  ORDER BY t.member;
            BEGIN
                total_income := (
                    SELECT sum(t.amount)
                      FROM payday_tips t
                      JOIN payday_participants p ON p.id = t.tipper
                     WHERE t.tippee = team_id
                       AND p.new_balance >= t.amount
                );
                total_takes := (
                    SELECT sum(t.amount)
                      FROM payday_takes t
                     WHERE t.team = team_id
                );
                IF (total_income = 0 OR total_takes = 0) THEN RETURN; END IF;
                ratio := min(total_income / total_takes, 1::numeric);

                OPEN our_takes;
                FETCH our_takes INTO take;
                FOR tip IN our_tips LOOP
                    LOOP
                        IF (take.amount = 0) THEN
                            FETCH our_takes INTO take;
                            IF (take IS NULL) THEN RETURN; END IF;
                        END IF;
                        amount := min(tip.amount, take.amount);
                        IF (tip.tipper <> take.member) THEN
                            UPDATE payday_tips SET is_funded = true WHERE id = tip.id;
                            EXECUTE transfer(tip.tipper, take.member, amount, 'take', team_id);
                        END IF;
                        tip.amount := tip.amount - amount;
                        take.amount := take.amount - amount;
                        EXIT WHEN tip.amount = 0;
                    END LOOP;
                END LOOP;
                RETURN;
            END;
        $$ LANGUAGE plpgsql;

        """, dict(ts_start=ts_start))
        log('Prepared the DB.')

    @staticmethod
    def transfer_virtually(cursor):
        cursor.run("""
            SELECT settle_tip_graph();
            SELECT resolve_takes(team) FROM payday_takes GROUP BY team ORDER BY team;
            SELECT settle_tip_graph();
        """)

    @staticmethod
    def check_balances(cursor):
        """Check that balances aren't becoming (more) negative
        """
        oops = cursor.one("""
            SELECT *
              FROM (
                     SELECT p.id
                          , p.username
                          , (p.balance + p2.new_balance - p2.old_balance) AS new_balance
                          , p.balance AS cur_balance
                       FROM payday_participants p2
                       JOIN participants p ON p.id = p2.id
                        AND p2.new_balance <> p2.old_balance
                   ) foo
             WHERE new_balance < 0 AND new_balance < cur_balance
             LIMIT 1
        """)
        if oops:
            log(oops)
            raise NegativeBalance()
        log("Checked the balances.")

    def transfer_for_real(self, transfers):
        db = self.db
        for t in transfers:
            transfer(db, **t.__dict__)

    def clean_up(self):
        self.db.run("""
            DROP FUNCTION process_tip();
            DROP FUNCTION settle_tip_graph();
            DROP FUNCTION transfer(bigint, bigint, numeric, transfer_context, bigint);
            DROP FUNCTION resolve_takes(bigint);
        """)

    def update_stats(self):
        self.db.run("""\

            WITH our_transfers AS (
                     SELECT *
                       FROM transfers
                      WHERE "timestamp" >= %(ts_start)s
                        AND status = 'succeeded'
                 )
               , our_tips AS (
                     SELECT *
                       FROM our_transfers
                      WHERE context = 'tip'
                 )
               , our_takes AS (
                     SELECT *
                       FROM our_transfers
                      WHERE context = 'take'
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
                 , ntippees = (SELECT count(DISTINCT tippee) FROM our_transfers)
                 , ntips = (SELECT count(*) FROM our_tips)
                 , ntakes = (SELECT count(*) FROM our_takes)
                 , take_volume = (SELECT COALESCE(sum(amount), 0) FROM our_takes)
                 , ntransfers = (SELECT count(*) FROM our_transfers)
                 , transfer_volume = (SELECT COALESCE(sum(amount), 0) FROM our_transfers)
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz

        """, {'ts_start': self.ts_start})
        log("Updated payday stats.")

    def update_cached_amounts(self):
        now = aspen.utils.utcnow()
        with self.db.get_cursor() as cursor:
            self.prepare(cursor, now)
            self.transfer_virtually(cursor)
            cursor.run("""

            UPDATE tips t
               SET is_funded = t2.is_funded
              FROM payday_tips t2
             WHERE t.id = t2.id
               AND t.is_funded <> t2.is_funded;

            UPDATE participants p
               SET giving = p2.giving
              FROM ( SELECT tipper AS id, sum(amount) AS giving
                       FROM payday_transfers
                   GROUP BY tipper
                   ) p2
             WHERE p.id = p2.id
               AND p.giving <> p2.giving;

            UPDATE participants p
               SET taking = p2.taking
              FROM ( SELECT tippee AS id, sum(amount) AS taking
                       FROM payday_transfers
                      WHERE context = 'take'
                   GROUP BY tippee
                   ) p2
             WHERE p.id = p2.id
               AND p.taking <> p2.taking;

            UPDATE participants p
               SET receiving = p2.receiving
              FROM ( SELECT tippee AS id, sum(amount) AS receiving
                       FROM payday_transfers
                   GROUP BY tippee
                   ) p2
             WHERE p.id = p2.id
               AND p.receiving <> p2.receiving;

            UPDATE participants p
               SET npatrons = p2.npatrons
              FROM ( SELECT tippee AS id, count(*) AS npatrons
                       FROM payday_transfers
                   GROUP BY tippee
                   ) p2
             WHERE p.id = p2.id
               AND p.npatrons <> p2.npatrons;

            """)
        self.clean_up()
        log("Updated receiving amounts.")

    def end(self):
        self.ts_end = self.db.one("""
            UPDATE paydays
               SET ts_end=now()
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING ts_end AT TIME ZONE 'UTC'
        """, default=NoPayday).replace(tzinfo=aspen.utils.utc)

    def notify_participants(self):
        previous_ts_end = self.db.one("""
            SELECT ts_end
              FROM paydays
             WHERE ts_start < %s
          ORDER BY ts_end DESC
             LIMIT 1
        """, (self.ts_start,), default=constants.BIRTHDAY)

        # Income notifications
        r = self.db.all("""
            SELECT tippee, json_agg(t) AS transfers
              FROM transfers t
             WHERE "timestamp" > %s
               AND "timestamp" <= %s
          GROUP BY tippee
        """, (previous_ts_end, self.ts_end))
        for tippee_id, transfers in r:
            successes = [t for t in transfers if t['status'] == 'succeeded']
            if not successes:
                continue
            by_team = {k: sum(t['amount'] for t in v)
                       for k, v in group_by(successes, 'team').items()}
            personal = by_team.pop(None, 0)
            by_team = {Participant.from_id(k).username: v for k, v in by_team.items()}
            Participant.from_id(tippee_id).notify(
                'income',
                total=sum(t['amount'] for t in successes),
                personal=personal,
                by_team=by_team,
            )

        # Low-balance notifications
        participants = self.db.all("""
            SELECT p.*::participants
              FROM participants p
             WHERE balance < giving
               AND giving > 0
               AND EXISTS (
                     SELECT 1
                       FROM transfers t
                      WHERE t.tipper = p.id
                        AND t.timestamp > %s
                        AND t.timestamp <= %s
                        AND t.status = 'succeeded'
                   )
        """, (previous_ts_end, self.ts_end))
        for p in participants:
            p.notify('low_balance')


if __name__ == '__main__':  # pragma: no cover
    from liberapay import wireup
    from liberapay.billing.exchanges import sync_with_mangopay

    # Wire things up.
    # ===============

    env = wireup.env()
    db = wireup.db(env)
    Payday.db = db
    wireup.billing(env)

    try:
        sync_with_mangopay(db)
        Payday.start().run()
    except KeyboardInterrupt:
        pass
    except:
        import traceback
        traceback.print_exc()
