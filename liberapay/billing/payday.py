from collections import namedtuple
from datetime import date
from decimal import Decimal, ROUND_UP
from itertools import chain
import os
import os.path
from subprocess import Popen
import sys
from time import sleep

from babel.dates import format_timedelta
import mangopay
import pando.utils
import requests

from liberapay import constants
from liberapay.billing.transactions import Money, transfer
from liberapay.exceptions import NegativeBalance
from liberapay.i18n.currencies import MoneyBasket
from liberapay.models.participant import Participant
from liberapay.utils import group_by
from liberapay.website import website


log = print


def round_up(d):
    return d.quantize(constants.D_CENT, rounding=ROUND_UP)


TakeTransfer = namedtuple('TakeTransfer', 'tipper member amount')


class NoPayday(Exception):
    __str__ = lambda self: "No payday found where one was expected."


class Payday(object):

    @classmethod
    def start(cls, public_log=''):
        """Try to start a new Payday.

        If there is a Payday that hasn't finished yet, then the UNIQUE
        constraint on ts_end will kick in and notify us of that. In that case
        we load the existing Payday and work on it some more. We use the start
        time of the current Payday to synchronize our work.

        """
        d = cls.db.one("""
            INSERT INTO paydays
                        (id, public_log, ts_start)
                 VALUES ( COALESCE((SELECT id FROM paydays ORDER BY id DESC LIMIT 1), 0) + 1
                        , %s
                        , now()
                        )
            ON CONFLICT (ts_end) DO UPDATE
                    SET ts_start = COALESCE(paydays.ts_start, excluded.ts_start)
              RETURNING id, (ts_start AT TIME ZONE 'UTC') AS ts_start, stage
        """, (public_log,), back_as=dict)
        log("Running payday #%s." % d['id'])

        d['ts_start'] = d['ts_start'].replace(tzinfo=pando.utils.utc)

        log("Payday started at %s." % d['ts_start'])

        payday = Payday()
        payday.__dict__.update(d)
        return payday

    def run(self, log_dir='.', keep_log=False, recompute_stats=10, update_cached_amounts=True):
        """This is the starting point for payday.

        It is structured such that it can be run again safely (with a
        newly-instantiated Payday object) if it crashes.

        """
        self.db.self_check()

        _start = pando.utils.utcnow()
        log("Greetings, program! It's PAYDAY!!!!")

        self.shuffle(log_dir)

        self.end()

        self.recompute_stats(limit=recompute_stats)
        if update_cached_amounts:
            self.update_cached_amounts()

        self.notify_participants()

        _end = pando.utils.utcnow()
        _delta = _end - _start
        msg = "Script ran for %s ({0})."
        log(msg.format(_delta) % format_timedelta(_delta, locale='en'))

        if keep_log:
            output_log_name = 'payday-%i.txt' % self.id
            output_log_path = log_dir+'/'+output_log_name
            if website.s3:
                s3_bucket = website.app_conf.s3_payday_logs_bucket
                s3_key = 'paydays/'+output_log_name
                website.s3.upload_file(output_log_path+'.part', s3_bucket, s3_key)
                log("Uploaded log to S3.")
            os.rename(output_log_path+'.part', output_log_path)

        self.db.run("UPDATE paydays SET stage = NULL WHERE id = %s", (self.id,))

    def shuffle(self, log_dir='.'):
        if self.stage > 2:
            return
        get_transfers = lambda: self.db.all("""
            SELECT t.*
                 , w.remote_owner_id AS tipper_mango_id
                 , w2.remote_owner_id AS tippee_mango_id
                 , w.remote_id AS tipper_wallet_id
                 , w2.remote_id AS tippee_wallet_id
              FROM payday_transfers t
         LEFT JOIN wallets w ON w.owner = t.tipper AND
                   w.balance::currency = t.amount::currency AND
                   w.is_current IS TRUE
         LEFT JOIN wallets w2 ON w2.owner = t.tippee AND
                   w2.balance::currency = t.amount::currency AND
                   w2.is_current IS TRUE
          ORDER BY t.id
        """)
        if self.stage == 2:
            transfers = get_transfers()
            done = self.db.all("""
                SELECT *
                  FROM transfers t
                 WHERE t.timestamp >= %(ts_start)s
                   AND status = 'succeeded'
            """, dict(ts_start=self.ts_start))
            done = set((t.tipper, t.tippee, t.context, t.team) for t in done)
            transfers = [t for t in transfers if (t.tipper, t.tippee, t.context, t.team) not in done]
        else:
            assert self.stage == 1
            with self.db.get_cursor() as cursor:
                self.prepare(cursor, self.ts_start)
                self.transfer_virtually(cursor, self.ts_start)
                self.check_balances(cursor)
                cursor.run("""
                    UPDATE paydays
                       SET nparticipants = (SELECT count(*) FROM payday_participants)
                     WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz;
                """)
                self.mark_stage_done(cursor)
            self.clean_up()
            transfers = get_transfers()

        self.transfer_for_real(transfers)
        self.settle_debts(self.db)

        self.db.self_check()
        self.mark_stage_done()
        self.db.run("DROP TABLE payday_transfers")

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
                 , status
                 , ( SELECT basket_sum(w.balance)
                       FROM wallets w
                      WHERE w.owner = p.id
                        AND w.is_current
                        AND %(use_mangopay)s
                   ) AS balances
                 , goal
                 , kind
                 , main_currency
                 , accepted_currencies
              FROM participants p
             WHERE join_time < %(ts_start)s
               AND is_suspended IS NOT true
               AND status <> 'stub'
          ORDER BY join_time;

        CREATE UNIQUE INDEX ON payday_participants (id);

        CREATE TEMPORARY TABLE payday_tips ON COMMIT DROP AS
            SELECT t.id, t.tipper, t.tippee, t.amount, (p2.kind = 'group') AS to_team
                 , coalesce_currency_amount(t.paid_in_advance, t.amount::currency) AS paid_in_advance
                 , ( t.renewal_mode > 0 AND (p2.goal IS NULL OR p2.goal >= 0) AND
                     p.status = 'active' AND p2.status = 'active'
                   ) AS process_real_transfers
              FROM ( SELECT DISTINCT ON (tipper, tippee) *
                       FROM tips
                      WHERE mtime < %(ts_start)s
                   ORDER BY tipper, tippee, mtime DESC
                   ) t
              JOIN payday_participants p ON p.id = t.tipper
              JOIN payday_participants p2 ON p2.id = t.tippee
             WHERE (p2.goal IS NULL OR p2.goal >= 0 OR t.paid_in_advance > t.amount)
          ORDER BY p.join_time ASC, t.ctime ASC;

        CREATE INDEX ON payday_tips (tipper);
        CREATE INDEX ON payday_tips (tippee);
        ALTER TABLE payday_tips ADD COLUMN is_funded boolean;

        CREATE TEMPORARY TABLE payday_takes ON COMMIT DROP AS
            SELECT team, member, amount, paid_in_advance
              FROM ( SELECT DISTINCT ON (team, member) *
                       FROM takes
                      WHERE mtime < %(ts_start)s
                   ORDER BY team, member, mtime DESC
                   ) t
             WHERE t.amount IS NOT NULL
               AND t.amount <> 0
               AND t.team IN (SELECT id FROM payday_participants)
               AND t.member IN (SELECT id FROM payday_participants);

        CREATE UNIQUE INDEX ON payday_takes (team, member);

        DROP TABLE IF EXISTS payday_transfers;
        CREATE TABLE payday_transfers
        ( id serial
        , tipper bigint
        , tippee bigint
        , amount currency_amount
        , in_advance currency_amount
        , context transfer_context
        , team bigint
        , invoice int
        , UNIQUE (tipper, tippee, context, team)
        );


        -- Prepare a statement that makes and records a transfer

        CREATE OR REPLACE FUNCTION transfer(
            a_tipper bigint,
            a_tippee bigint,
            a_amount currency_amount,
            a_context transfer_context,
            a_team bigint,
            a_invoice int
        )
        RETURNS void AS $$
            DECLARE
                in_advance currency_amount;
                tip payday_tips;
                transfer_amount currency_amount;
            BEGIN
                IF (a_amount = 0) THEN RETURN; END IF;
                in_advance := zero(a_amount);
                transfer_amount := a_amount;

                IF (a_context IN ('tip', 'take')) THEN
                    tip := (
                        SELECT t
                          FROM payday_tips t
                         WHERE t.tipper = a_tipper
                           AND t.tippee = COALESCE(a_team, a_tippee)
                    );
                    IF (tip IS NULL) THEN
                        RAISE 'tip not found: %%, %%, %%', a_tipper, a_tippee, a_team;
                    END IF;
                    IF (tip.paid_in_advance > 0) THEN
                        IF (tip.paid_in_advance >= transfer_amount) THEN
                            in_advance := transfer_amount;
                        ELSE
                            in_advance := tip.paid_in_advance;
                        END IF;
                        transfer_amount := transfer_amount - in_advance;
                    END IF;
                    IF (NOT tip.process_real_transfers) THEN
                        transfer_amount := zero(transfer_amount);
                    END IF;
                END IF;

                UPDATE payday_participants
                   SET balances = (balances - transfer_amount)
                 WHERE id = a_tipper;
                IF (NOT FOUND) THEN RAISE 'tipper %% not found', a_tipper; END IF;
                UPDATE payday_participants
                   SET balances = (balances + transfer_amount)
                 WHERE id = a_tippee;
                IF (NOT FOUND) THEN RAISE 'tippee %% not found', a_tippee; END IF;
                INSERT INTO payday_transfers
                            (tipper, tippee, amount, in_advance, context, team, invoice)
                     VALUES (a_tipper, a_tippee, transfer_amount, in_advance, a_context, a_team, a_invoice);
            END;
        $$ LANGUAGE plpgsql;


        -- Create a function to check whether a tip is "funded" or not

        CREATE OR REPLACE FUNCTION check_tip_funding(payday_tips) RETURNS boolean AS $$
            DECLARE
                tipper_balances currency_basket;
                okay boolean = false;
            BEGIN
                IF ($1.is_funded IS true) THEN RETURN NULL; END IF;
                okay := $1.paid_in_advance >= $1.amount;
                IF (okay IS NOT true) THEN
                    IF (NOT $1.process_real_transfers) THEN
                        RETURN false;
                    END IF;
                    tipper_balances := (
                        SELECT balances
                          FROM payday_participants p
                         WHERE id = $1.tipper
                    );
                    okay := tipper_balances >= ($1.amount - $1.paid_in_advance);
                END IF;
                RETURN okay;
            END;
        $$ LANGUAGE plpgsql;


        -- Create a function to settle one-to-one donations

        CREATE OR REPLACE FUNCTION settle_tip_graph() RETURNS void AS $$
            DECLARE
                count integer NOT NULL DEFAULT 0;
                i integer := 0;
            BEGIN
                LOOP
                    i := i + 1;
                    WITH updated_rows AS (
                         UPDATE payday_tips AS t
                            SET is_funded = true
                          WHERE is_funded IS NOT true
                            AND to_team IS NOT true
                            AND check_tip_funding(t) IS true
                      RETURNING id, transfer(tipper, tippee, amount, 'tip', NULL, NULL)
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

        """, dict(ts_start=ts_start, use_mangopay=mangopay.sandbox))
        log("Prepared the DB.")

    @staticmethod
    def transfer_virtually(cursor, ts_start):
        cursor.run("SELECT settle_tip_graph();")
        teams = cursor.all("""
            SELECT id, main_currency FROM payday_participants WHERE kind = 'group';
        """)
        for team_id, currency in teams:
            Payday.transfer_takes(cursor, team_id, currency)
        cursor.run("""
            SELECT settle_tip_graph();
            UPDATE payday_tips SET is_funded = false WHERE is_funded IS NULL;
        """)
        Payday.pay_invoices(cursor, ts_start)

    @staticmethod
    def transfer_takes(cursor, team_id, currency):
        """Resolve and transfer takes for the specified team
        """
        args = dict(team_id=team_id)
        tips = cursor.all("""
            UPDATE payday_tips AS t
               SET is_funded = true
             WHERE tippee = %(team_id)s
               AND check_tip_funding(t) IS true
         RETURNING t.id, t.tipper, t.amount AS full_amount, t.paid_in_advance
                 , ( SELECT p.balances
                       FROM payday_participants p
                      WHERE p.id = t.tipper
                   ) AS balances
                 , coalesce_currency_amount((
                       SELECT sum(tr.amount, t.amount::currency)
                         FROM transfers tr
                        WHERE tr.tipper = t.tipper
                          AND tr.team = %(team_id)s
                          AND tr.context = 'take'
                          AND tr.status = 'succeeded'
                   ), t.amount::currency) AS past_transfers_sum
        """, args)
        takes = cursor.all("""
            SELECT t.member, t.amount, t.paid_in_advance
                 , p.main_currency, p.accepted_currencies
              FROM payday_takes t
              JOIN payday_participants p ON p.id = t.member
             WHERE t.team = %(team_id)s;
        """, args)
        transfers, leftover = Payday.resolve_takes(tips, takes, currency)
        for t in transfers:
            cursor.run("SELECT transfer(%s, %s, %s, 'take', %s, NULL)",
                       (t.tipper, t.member, t.amount, team_id))

    @staticmethod
    def resolve_takes(tips, takes, ref_currency):
        """Resolve many-to-many donations (team takes)
        """
        total_income = MoneyBasket(t.full_amount for t in tips)
        if total_income == 0:
            return (), total_income
        if mangopay.sandbox:
            takes = [t for t in takes if t.amount != 0]
        else:
            takes = [t for t in takes if t.amount != 0 and t.paid_in_advance]
        if not takes:
            return (), total_income
        fuzzy_income_sum = total_income.fuzzy_sum(ref_currency)
        manual_takes = [t for t in takes if t.amount > 0]
        if manual_takes:
            manual_takes_sum = MoneyBasket(t.amount for t in manual_takes)
            auto_take = fuzzy_income_sum - manual_takes_sum.fuzzy_sum(ref_currency)
            if auto_take < 0:
                auto_take = auto_take.zero()
        else:
            auto_take = fuzzy_income_sum
        for take in takes:
            if take.amount < 0:
                take.amount = auto_take.convert(take.amount.currency)
            assert take.amount >= 0
        total_takes = MoneyBasket(t.amount for t in takes)
        fuzzy_takes_sum = total_takes.fuzzy_sum(ref_currency)
        tips_by_currency = group_by(tips, lambda t: t.full_amount.currency)
        takes_by_preferred_currency = group_by(takes, lambda t: t.main_currency)
        takes_by_secondary_currency = {c: [] for c in tips_by_currency}
        takes_ratio = min(fuzzy_income_sum / fuzzy_takes_sum, 1)
        for take in takes:
            take.amount = (take.amount * takes_ratio).round_up()
            if take.paid_in_advance is None:
                take.paid_in_advance = take.amount.zero()
            if take.accepted_currencies is None:
                take.accepted_currencies = constants.CURRENCIES
            else:
                take.accepted_currencies = take.accepted_currencies.split(',')
            for accepted in take.accepted_currencies:
                skip = (
                    accepted == take.main_currency or
                    accepted not in takes_by_secondary_currency
                )
                if skip:
                    continue
                takes_by_secondary_currency[accepted].append(take)
        tips_ratio = min(fuzzy_takes_sum / fuzzy_income_sum, 1)
        adjust_tips = tips_ratio != 1
        if adjust_tips:
            # The team has a leftover, so donation amounts can be adjusted.
            # In the following loop we compute the "weeks" count of each tip.
            # For example the `weeks` value is 2.5 for a donation currently at
            # 10€/week which has distributed 25€ in the past.
            for tip in tips:
                tip.weeks = round_up(tip.past_transfers_sum / tip.full_amount)
            max_weeks = max(tip.weeks for tip in tips)
            min_weeks = min(tip.weeks for tip in tips)
            adjust_tips = max_weeks != min_weeks
            if adjust_tips:
                # Some donors have given fewer weeks worth of money than others,
                # we want to adjust the amounts so that the weeks count will
                # eventually be the same for every donation.
                min_tip_ratio = tips_ratio * Decimal('0.1')
                # Loop: compute how many "weeks" each tip is behind the "oldest"
                # tip, as well as a naive ratio and amount based on that number
                # of weeks
                for tip in tips:
                    tip.weeks_to_catch_up = max_weeks - tip.weeks
                    tip.ratio = min(min_tip_ratio + tip.weeks_to_catch_up, 1)
                    tip.amount = (tip.full_amount * tip.ratio).round_up()
                naive_amounts_sum = MoneyBasket(tip.amount for tip in tips).fuzzy_sum(ref_currency)
                total_to_transfer = min(fuzzy_takes_sum, fuzzy_income_sum)
                delta = total_to_transfer - naive_amounts_sum
                if delta == 0:
                    # The sum of the naive amounts computed in the previous loop
                    # matches the end target, we got very lucky and no further
                    # adjustments are required
                    adjust_tips = False
                else:
                    # Loop: compute the "leeway" of each tip, i.e. how much it
                    # can be increased or decreased to fill the `delta` gap
                    if delta < 0:
                        # The naive amounts are too high: we want to lower the
                        # amounts of the tips that have a "high" ratio, leaving
                        # untouched the ones that are already low
                        for tip in tips:
                            if tip.ratio > min_tip_ratio:
                                min_tip_amount = (tip.full_amount * min_tip_ratio).round_up()
                                tip.leeway = min_tip_amount - tip.amount
                            else:
                                tip.leeway = tip.amount.zero()
                    else:
                        # The naive amounts are too low: we can raise all the
                        # tips that aren't already at their maximum
                        for tip in tips:
                            tip.leeway = tip.full_amount - tip.amount
                    leeway = MoneyBasket(tip.leeway for tip in tips).fuzzy_sum(ref_currency)
                    if leeway == 0:
                        # We don't actually have any leeway, give up
                        adjust_tips = False
                    else:
                        leeway_ratio = min(delta / leeway, 1)
                        tips = sorted(tips, key=lambda tip: (-tip.weeks_to_catch_up, tip.id))
        # Loop: compute the adjusted donation amounts, and do the transfers
        transfers = []
        for tip in tips:
            if tip.paid_in_advance is None:
                tip.paid_in_advance = tip.full_amount.zero()
            if adjust_tips:
                tip_amount = (tip.amount + tip.leeway * leeway_ratio).round_up()
                if tip_amount == 0:
                    continue
                assert tip_amount > 0
                assert tip_amount <= tip.full_amount
                tip.amount = tip_amount
            else:
                tip.amount = (tip.full_amount * tips_ratio).round_up()
            tip_currency = tip.amount.currency
            sorted_takes = chain(
                takes_by_preferred_currency.get(tip_currency, ()),
                takes_by_secondary_currency.get(tip_currency, ()),
                takes
            )
            for take in sorted_takes:
                if take.amount == 0 or tip.tipper == take.member:
                    continue
                fuzzy_take_amount = take.amount.convert(tip_currency)
                in_advance_amount = min(
                    tip.amount,
                    fuzzy_take_amount,
                    max(tip.paid_in_advance, 0),
                    max(take.paid_in_advance.convert(tip_currency), 0),
                )
                on_time_amount = min(
                    max(tip.amount - in_advance_amount, 0),
                    max(fuzzy_take_amount - in_advance_amount, 0),
                    tip.balances[tip_currency],
                )
                transfer_amount = in_advance_amount + on_time_amount
                if transfer_amount == 0:
                    continue
                transfers.append(TakeTransfer(tip.tipper, take.member, transfer_amount))
                if transfer_amount == fuzzy_take_amount:
                    take.amount = take.amount.zero()
                else:
                    take.amount -= transfer_amount.convert(take.amount.currency)
                if in_advance_amount:
                    tip.paid_in_advance -= in_advance_amount
                    take.paid_in_advance -= in_advance_amount.convert(take.amount.currency)
                if on_time_amount:
                    tip.balances -= on_time_amount
                tip.amount -= transfer_amount
                if tip.amount == 0:
                    break
        leftover = total_income - MoneyBasket(t.amount for t in transfers)
        return transfers, leftover

    @staticmethod
    def pay_invoices(cursor, ts_start):
        """Settle pending invoices
        """
        invoices = cursor.all("""
            SELECT i.*
              FROM invoices i
             WHERE i.status = 'accepted'
               AND ( SELECT ie.ts
                       FROM invoice_events ie
                      WHERE ie.invoice = i.id
                   ORDER BY ts DESC
                      LIMIT 1
                   ) < %(ts_start)s;
        """, dict(ts_start=ts_start))
        for i in invoices:
            can_pay = cursor.one("""
                SELECT p.balances >= %s AS can_pay
                  FROM payday_participants p
                 WHERE id = %s
            """, (i.amount, i.addressee))
            if not can_pay:
                continue
            cursor.run("""
                SELECT transfer(%(addressee)s, %(sender)s, %(amount)s,
                                %(nature)s::transfer_context, NULL, %(id)s);
                UPDATE invoices
                   SET status = 'paid'
                 WHERE id = %(id)s;
                INSERT INTO invoice_events
                            (invoice, participant, status)
                     VALUES (%(id)s, %(addressee)s, 'paid');
            """, i._asdict())

    @staticmethod
    def check_balances(cursor):
        """Check that balances aren't becoming (more) negative
        """
        oops = cursor.one("""
            SELECT p.id
                 , p.username
                 , p2.balances
              FROM payday_participants p2
              JOIN participants p ON p.id = p2.id
             WHERE p2.balances->'EUR' < 0 OR p2.balances->'USD' < 0
             LIMIT 1
        """)
        if oops:
            log(oops)
            raise NegativeBalance()
        log("Checked the balances.")

    def transfer_for_real(self, transfers):
        db = self.db
        print("Starting transfers (n=%i)" % len(transfers))
        msg = "%s transfer #%i (amount=%s in_advance=%s context=%s team=%s)%s"
        for t in transfers:
            if t.amount:
                delay = getattr(self, 'transfer_delay', 0)
                action = 'Executing'
                when = ' in %.2f seconds' % delay if delay else ' now'
            else:
                delay = 0
                action = 'Recording'
                when = ''
            log(msg % (action, t.id, t.amount, t.in_advance, t.context, t.team, when))
            if delay:
                sleep(delay)
            if t.in_advance:
                db.run("""
                    INSERT INTO transfers
                                (tipper, tippee, amount, context,
                                 team, invoice, status,
                                 wallet_from, wallet_to, virtual)
                         VALUES (%(tipper)s, %(tippee)s, %(in_advance)s, %(context)s,
                                 %(team)s, %(invoice)s, 'succeeded',
                                 'x', 'y', true);

                    WITH current_tip AS (
                             SELECT t.id
                               FROM current_tips t
                              WHERE t.tipper = %(tipper)s
                                AND t.tippee = COALESCE(%(team)s, %(tippee)s)
                         )
                    UPDATE tips t
                       SET paid_in_advance = (t.paid_in_advance - %(in_advance)s)
                      FROM current_tip t2
                     WHERE t.id = t2.id;
                """, t.__dict__)
                if t.team:
                    db.run("""
                        WITH current_take AS (
                                 SELECT t.id
                                   FROM current_takes t
                                  WHERE t.team = %(team)s
                                    AND t.member = %(tippee)s
                             )
                        UPDATE takes t
                           SET paid_in_advance = (
                                   coalesce_currency_amount(t.paid_in_advance, t.amount::currency) -
                                   convert(%(in_advance)s, t.amount::currency)
                               )
                          FROM current_take t2
                         WHERE t.id = t2.id;
                    """, t.__dict__)
            if t.amount:
                transfer(db, **t.__dict__)

    @classmethod
    def clean_up(cls):
        cls.db.run("""
            DROP FUNCTION settle_tip_graph();
            DROP FUNCTION transfer(bigint, bigint, currency_amount, transfer_context, bigint, int);
        """)

    @staticmethod
    def settle_debts(db):
        while True:
            with db.get_cursor() as cursor:
                debt = cursor.one("""
                    SELECT d.id, d.debtor AS tipper, d.creditor AS tippee, d.amount
                         , 'debt' AS context
                         , w_debtor.remote_owner_id AS tipper_mango_id
                         , w_debtor.remote_id AS tipper_wallet_id
                         , w_creditor.remote_owner_id AS tippee_mango_id
                         , w_creditor.remote_id AS tippee_wallet_id
                      FROM debts d
                      JOIN wallets w_debtor ON w_debtor.owner = d.debtor AND
                           w_debtor.balance::currency = d.amount::currency AND
                           w_debtor.is_current IS TRUE
                 LEFT JOIN wallets w_creditor ON w_creditor.owner = d.creditor AND
                           w_creditor.balance::currency = d.amount::currency AND
                           w_creditor.is_current IS TRUE
                      JOIN participants p_creditor ON p_creditor.id = d.creditor
                     WHERE d.status = 'due'
                       AND w_debtor.balance >= d.amount
                       AND p_creditor.status = 'active'
                     LIMIT 1
                       FOR UPDATE OF d
                """)
                if not debt:
                    break
                try:
                    t_id = transfer(db, **debt._asdict())[1]
                except NegativeBalance:
                    continue
                cursor.run("""
                    UPDATE debts
                       SET status = 'paid'
                         , settlement = %s
                     WHERE id = %s
                """, (t_id, debt.id))

    @classmethod
    def update_stats(cls, payday_id):
        ts_start, ts_end = cls.db.one("""
            SELECT ts_start, ts_end FROM paydays WHERE id = %s
        """, (payday_id,))
        if payday_id > 1:
            previous_ts_start = cls.db.one("""
                SELECT ts_start
                  FROM paydays
                 WHERE id = %s
            """, (payday_id - 1,))
        else:
            previous_ts_start = constants.EPOCH
        assert previous_ts_start
        cls.db.run("""\

            WITH our_transfers AS (
                     SELECT *
                       FROM transfers
                      WHERE "timestamp" >= %(ts_start)s
                        AND "timestamp" <= %(ts_end)s
                        AND status = 'succeeded'
                        AND context IN ('tip', 'take')
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
               , week_exchanges AS (
                     SELECT e.*
                          , ( EXISTS (
                                SELECT e2.id
                                  FROM exchanges e2
                                 WHERE e2.refund_ref = e.id
                            )) AS refunded
                       FROM exchanges e
                      WHERE e.timestamp < %(ts_start)s
                        AND e.timestamp >= %(previous_ts_start)s
                        AND status <> 'failed'
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
                 , take_volume = (SELECT basket_sum(amount) FROM our_takes)
                 , ntransfers = (SELECT count(*) FROM our_transfers)
                 , transfer_volume = (SELECT basket_sum(amount) FROM our_transfers)
                 , transfer_volume_refunded = (
                       SELECT basket_sum(amount)
                         FROM our_transfers
                        WHERE refund_ref IS NOT NULL
                   )
                 , nusers = (
                       SELECT count(*)
                         FROM participants p
                        WHERE p.kind IN ('individual', 'organization')
                          AND p.join_time < %(ts_start)s
                          AND COALESCE((
                                SELECT payload::text
                                  FROM events e
                                 WHERE e.participant = p.id
                                   AND e.type = 'set_status'
                                   AND e.ts < %(ts_start)s
                              ORDER BY ts DESC
                                 LIMIT 1
                              ), '') <> '"closed"'
                   )
                 , week_deposits = (
                       SELECT basket_sum(amount)
                         FROM week_exchanges
                        WHERE amount > 0
                          AND refund_ref IS NULL
                          AND status = 'succeeded'
                   )
                 , week_deposits_refunded = (
                       SELECT basket_sum(amount)
                         FROM week_exchanges
                        WHERE amount > 0
                          AND refunded
                   )
                 , week_withdrawals = (
                       SELECT basket_sum(-amount)
                         FROM week_exchanges
                        WHERE amount < 0
                          AND refund_ref IS NULL
                   )
                 , week_withdrawals_refunded = (
                       SELECT basket_sum(amount)
                         FROM week_exchanges
                        WHERE amount < 0
                          AND refunded
                   )
                 , week_payins = (
                       SELECT basket_sum(pi.amount)
                         FROM payins pi
                        WHERE pi.ctime < %(ts_start)s
                          AND pi.ctime >= %(previous_ts_start)s
                          AND pi.status = 'succeeded'
                   )
             WHERE id = %(payday_id)s

        """, locals())
        log("Updated stats of payday #%i." % payday_id)

    @classmethod
    def recompute_stats(cls, limit=None):
        ids = cls.db.all("""
            SELECT id
              FROM paydays
             WHERE ts_end > ts_start
          ORDER BY id DESC
             LIMIT %s
        """, (limit,))
        for payday_id in ids:
            cls.update_stats(payday_id)

    @classmethod
    def update_cached_amounts(cls):
        now = pando.utils.utcnow()
        with cls.db.get_cursor() as cursor:
            cursor.run("LOCK TABLE takes IN EXCLUSIVE MODE")
            cls.prepare(cursor, now)
            cls.transfer_virtually(cursor, now)
            cursor.run("""

            UPDATE tips t
               SET is_funded = t2.is_funded
              FROM payday_tips t2
             WHERE t.id = t2.id
               AND t.is_funded <> t2.is_funded;

            WITH active_donors AS (
                     SELECT DISTINCT tr.tipper AS id
                       FROM transfers tr
                      WHERE tr.context IN ('tip', 'take')
                        AND tr.timestamp > (current_timestamp - interval '30 days')
                        AND tr.status = 'succeeded'
                      UNION
                     SELECT DISTINCT pi.payer AS id
                       FROM payins pi
                      WHERE pi.ctime > (current_timestamp - interval '30 days')
                        AND pi.status = 'succeeded'
                 )
            UPDATE tips t
               SET is_funded = t2.is_funded
              FROM ( SELECT t2.id, (t2.tipper IN (SELECT ad.id FROM active_donors ad)) AS is_funded
                       FROM current_tips t2
                       JOIN participants tippee_p ON tippee_p.id = t2.tippee
                      WHERE tippee_p.status = 'stub'
                   ) t2
             WHERE t2.id = t.id
               AND t.is_funded <> t2.is_funded;

            UPDATE participants p
               SET receiving = p2.receiving
              FROM ( SELECT p2.id
                          , coalesce_currency_amount(
                                sum(t.amount, p2.main_currency),
                                p2.main_currency
                            ) AS receiving
                       FROM current_tips t
                       JOIN participants p2 ON p2.id = t.tippee
                      WHERE p2.status = 'stub'
                        AND t.is_funded
                   GROUP BY p2.id
                   ) p2
             WHERE p.id = p2.id
               AND p.receiving <> p2.receiving
               AND p.status = 'stub';

            UPDATE takes t
               SET actual_amount = t2.actual_amount
              FROM ( SELECT t2.id
                          , (
                                SELECT basket_sum(tr.amount + tr.in_advance)
                                  FROM payday_transfers tr
                                 WHERE tr.team = t2.team
                                   AND tr.tippee = t2.member
                                   AND tr.context = 'take'
                            ) AS actual_amount
                       FROM current_takes t2
                   ) t2
             WHERE t.id = t2.id
               AND t.actual_amount <> t2.actual_amount;

            UPDATE participants p
               SET giving = p2.giving
              FROM ( SELECT p2.id
                          , coalesce_currency_amount((
                                SELECT sum(amount, p2.main_currency)
                                  FROM payday_tips t
                                 WHERE t.tipper = p2.id
                                   AND t.is_funded
                            ), p2.main_currency) AS giving
                       FROM participants p2
                   ) p2
             WHERE p.id = p2.id
               AND p.giving <> p2.giving;

            UPDATE participants p
               SET taking = p2.taking
              FROM ( SELECT p2.id
                          , coalesce_currency_amount((
                                SELECT sum(t.amount + t.in_advance, p2.main_currency)
                                  FROM payday_transfers t
                                 WHERE t.tippee = p2.id
                                   AND context = 'take'
                            ), p2.main_currency) AS taking
                       FROM participants p2
                   ) p2
             WHERE p.id = p2.id
               AND p.taking <> p2.taking;

            UPDATE participants p
               SET receiving = p2.receiving
              FROM ( SELECT p2.id
                          , p2.taking + coalesce_currency_amount((
                                SELECT sum(amount, p2.main_currency)
                                  FROM payday_tips t
                                 WHERE t.tippee = p2.id
                                   AND t.is_funded
                            ), p2.main_currency) AS receiving
                       FROM participants p2
                   ) p2
             WHERE p.id = p2.id
               AND p.receiving <> p2.receiving
               AND p.status <> 'stub';

            UPDATE participants p
               SET leftover = p2.leftover
              FROM ( SELECT p2.id
                          , (
                                SELECT basket_sum(t.amount)
                                  FROM payday_tips t
                                 WHERE t.tippee = p2.id
                                   AND t.is_funded
                            ) - (
                                SELECT basket_sum(t.amount + t.in_advance)
                                  FROM payday_transfers t
                                 WHERE t.tippee = p2.id
                                    OR t.team = p2.id
                            ) AS leftover
                       FROM participants p2
                   ) p2
             WHERE p.id = p2.id
               AND p.leftover <> p2.leftover;

            UPDATE participants p
               SET nteampatrons = p2.nteampatrons
              FROM ( SELECT p2.id
                          , ( SELECT count(DISTINCT t.tipper)
                                FROM payday_transfers t
                               WHERE t.tippee = p2.id
                                 AND t.context = 'take'
                            ) AS nteampatrons
                       FROM participants p2
                      WHERE p2.status <> 'stub'
                        AND p2.kind IN ('individual', 'organization')
                   ) p2
             WHERE p.id = p2.id
               AND p.nteampatrons <> p2.nteampatrons;

            UPDATE participants p
               SET npatrons = p2.npatrons
              FROM ( SELECT p2.id
                          , ( SELECT count(*)
                                FROM payday_tips t
                               WHERE t.tippee = p2.id
                                 AND t.is_funded
                            ) AS npatrons
                       FROM participants p2
                      WHERE p2.status <> 'stub'
                   ) p2
             WHERE p.id = p2.id
               AND p.npatrons <> p2.npatrons;

            """)
        cls.clean_up()
        log("Updated receiving amounts.")

    def mark_stage_done(self, cursor=None):
        self.stage = (cursor or self.db).one("""
            UPDATE paydays
               SET stage = stage + 1
             WHERE id = %s
         RETURNING stage
        """, (self.id,), default=NoPayday)

    def end(self):
        self.ts_end = self.db.one("""
            UPDATE paydays
               SET ts_end=now()
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING ts_end AT TIME ZONE 'UTC'
        """, default=NoPayday).replace(tzinfo=pando.utils.utc)

    def notify_participants(self):
        previous_ts_end = self.db.one("""
            SELECT ts_end
              FROM paydays
             WHERE ts_start < %s
          ORDER BY ts_end DESC
             LIMIT 1
        """, (self.ts_start,), default=constants.BIRTHDAY)

        # Income notifications
        n = 0
        r = self.db.all("""
            SELECT tippee, json_agg(t) AS transfers
              FROM transfers t
             WHERE "timestamp" > %s
               AND "timestamp" <= %s
               AND context IN ('tip', 'take', 'final-gift')
               AND status = 'succeeded'
          GROUP BY tippee
          ORDER BY tippee
        """, (previous_ts_end, self.ts_end))
        for tippee_id, transfers in r:
            p = Participant.from_id(tippee_id)
            if p.status != 'active' or not p.accepts_tips:
                continue
            for t in transfers:
                t['amount'] = Money(**t['amount'])
            by_team = {
                k: (
                    MoneyBasket(t['amount'] for t in v).fuzzy_sum(p.main_currency),
                    len(set(t['tipper'] for t in v))
                ) for k, v in group_by(transfers, 'team').items()
            }
            total = sum((t[0] for t in by_team.values()), MoneyBasket())
            nothing = (MoneyBasket(), 0)
            personal, personal_npatrons = by_team.pop(None, nothing)
            teams = p.get_teams()
            team_ids = set(t.id for t in teams) | set(by_team.keys())
            team_names = {t.id: t.name for t in teams}
            get_username = lambda i: team_names.get(i) or self.db.one(
                "SELECT username FROM participants WHERE id = %s", (i,)
            )
            by_team = {get_username(t_id): by_team.get(t_id, nothing) for t_id in team_ids}
            p.notify(
                'income~v2',
                total=total.fuzzy_sum(p.main_currency),
                personal=personal,
                personal_npatrons=personal_npatrons,
                by_team=by_team,
                mangopay_balance=p.get_balances(),
            )
            n += 1
        log("Sent %i income notifications." % n)

        # Donation renewal notifications
        n = 0
        participants = self.db.all("""
            SELECT (SELECT p FROM participants p WHERE p.id = t.tipper) AS p
                 , json_agg((SELECT a FROM (
                       SELECT t.periodic_amount, t.tippee_username
                   ) a))
              FROM (
                     SELECT t.*, tippee_p.username AS tippee_username
                       FROM current_tips t
                       JOIN participants tippee_p ON tippee_p.id = t.tippee
                      WHERE t.renewal_mode > 0
                        AND ( t.paid_in_advance IS NULL OR
                              t.paid_in_advance < t.amount
                            )
                        AND tippee_p.status = 'active'
                        AND tippee_p.is_suspended IS NOT true
                        AND tippee_p.payment_providers > 0
                        AND ( tippee_p.goal IS NULL OR tippee_p.goal >= 0 )
                   ) t
             WHERE EXISTS (
                     SELECT 1
                       FROM transfers tr
                      WHERE tr.tipper = t.tipper
                        AND COALESCE(tr.team, tr.tippee) = t.tippee
                        AND tr.context IN ('tip', 'take')
                        AND tr.status = 'succeeded'
                        AND tr.timestamp >= (current_date - interval '26 weeks')
                   )
               AND NOT EXISTS (
                     SELECT 1
                       FROM notifications n
                      WHERE n.participant = t.tipper
                        AND n.event = 'donate_reminder'
                        AND n.ts >= (current_date - interval '30 days')
                        AND n.is_new
                   )
               AND NOT EXISTS (
                     SELECT 1
                       FROM payin_transfers pt
                      WHERE pt.payer = t.tipper
                        AND COALESCE(pt.team, pt.recipient) = t.tippee
                        AND pt.context IN ('personal-donation', 'team-donation')
                        AND pt.status = 'pending'
                        AND pt.ctime >= (current_date - interval '30 days')
                   )
          GROUP BY t.tipper
          ORDER BY t.tipper
        """)
        for p, donations in participants:
            if p.status != 'active' or p.is_suspended:
                continue
            for tip in donations:
                tip['periodic_amount'] = Money(**tip['periodic_amount'])
            p.notify('donate_reminder', donations=donations, email_unverified_address=True)
            n += 1
        log("Sent %i donate_reminder notifications." % n)


def create_payday_issue():
    # Make sure today is payday
    today = date.today()
    today_weekday = today.isoweekday()
    today_is_wednesday = today_weekday == 3
    assert today_is_wednesday, today_weekday
    # Fetch last payday from DB
    last_payday = website.db.one("SELECT * FROM paydays ORDER BY id DESC LIMIT 1")
    if last_payday:
        last_start = last_payday.ts_start
        if last_start is None or last_start.date() == today:
            return
    next_payday_id = str(last_payday.id + 1 if last_payday else 1)
    # Prepare to make API requests
    app_conf = website.app_conf
    sess = requests.Session()
    sess.auth = (app_conf.bot_github_username, app_conf.bot_github_token)
    github = website.platforms.github
    label, repo = app_conf.payday_label, app_conf.payday_repo
    # Fetch the previous payday issue
    path = '/repos/%s/issues' % repo
    params = {'state': 'all', 'labels': label, 'per_page': 1}
    r = github.api_get('', path, params=params, sess=sess).json()
    last_issue = r[0] if r else None
    # Create the next payday issue
    next_issue = {'body': '', 'labels': [label]}
    if last_issue:
        last_issue_payday_id = str(int(last_issue['title'].split()[-1].lstrip('#')))
        if last_issue_payday_id == next_payday_id:
            return  # already created
        assert last_issue_payday_id == str(last_payday.id)
        next_issue['title'] = last_issue['title'].replace(last_issue_payday_id, next_payday_id)
        next_issue['body'] = last_issue['body']
    else:
        next_issue['title'] = "Payday #%s" % next_payday_id
    next_issue = github.api_request('POST', '', '/repos/%s/issues' % repo, json=next_issue, sess=sess).json()
    website.db.run("""
        INSERT INTO paydays
                    (id, public_log, ts_start)
             VALUES (%s, %s, NULL)
    """, (next_payday_id, next_issue['html_url']))


def payday_preexec():  # pragma: no cover
    # Tweak env
    from os import environ
    environ['CACHE_STATIC'] = 'no'
    environ['CLEAN_ASSETS'] = 'no'
    environ['RUN_CRON_JOBS'] = 'no'
    environ['PYTHONPATH'] = website.project_root
    # Write PID file
    pid_file = open(website.env.log_dir+'/payday.pid', 'w')
    pid_file.write(str(os.getpid()))


def exec_payday(log_file):  # pragma: no cover
    # Fork twice, like a traditional unix daemon
    if os.fork():
        return
    if os.fork():
        os.execlp('true', 'true')
    # Fork again and exec
    devnull = open(os.devnull)
    Popen(
        [sys.executable, '-u', 'liberapay/billing/payday.py'],
        stdin=devnull, stdout=log_file, stderr=log_file,
        close_fds=True, cwd=website.project_root, preexec_fn=payday_preexec,
    )
    os.execlp('true', 'true')


def main(override_payday_checks=False):
    from liberapay.billing.transactions import sync_with_mangopay
    from liberapay.main import website
    from liberapay.payin import paypal

    # https://github.com/liberapay/salon/issues/19#issuecomment-191230689
    from liberapay.billing.payday import Payday

    if not website.env.override_payday_checks and not override_payday_checks:
        # Check that payday hasn't already been run this week
        r = website.db.one("""
            SELECT id
              FROM paydays
             WHERE ts_start >= now() - INTERVAL '6 days'
               AND ts_end >= ts_start
        """)
        assert not r, "payday has already been run this week"

    # Prevent a race condition, by acquiring a DB lock
    with website.db.lock('payday', blocking=False):
        try:
            sync_with_mangopay(website.db)
            paypal.sync_all_pending_payments(website.db)
            Payday.start().run(website.env.log_dir, website.env.keep_payday_logs)
        except KeyboardInterrupt:  # pragma: no cover
            pass
        except Exception as e:  # pragma: no cover
            website.tell_sentry(e, {}, allow_reraise=False)
            raise


if __name__ == '__main__':  # pragma: no cover
    main()
