from datetime import date, timedelta
from decimal import Decimal, ROUND_UP
from itertools import chain
from operator import attrgetter
import os
import os.path
from subprocess import Popen
import sys

from babel.dates import format_timedelta
import pando.utils
import requests

from liberapay import constants
from liberapay.i18n.currencies import D_CENT, Money, MoneyBasket
from liberapay.payin.common import resolve_amounts
from liberapay.utils import group_by
from liberapay.website import website


log = print


def round_up(d):
    return d.quantize(D_CENT, rounding=ROUND_UP)


class TakeTransfer:
    __slots__ = ('tipper', 'member', 'amount', 'is_leftover', 'is_partial')

    def __init__(self, tipper, member, amount, is_leftover=False, is_partial=False):
        self.tipper = tipper
        self.member = member
        self.amount = amount
        self.is_leftover = is_leftover
        self.is_partial = is_partial

    def __repr__(self):
        return (
            f"TakeTransfer({self.tipper!r}, {self.member!r}, {self.amount!r}, "
            f"is_leftover={self.is_leftover!r}, is_partial={self.is_partial!r})"
        )


class NoPayday(Exception):
    __str__ = lambda self: "No payday found where one was expected."


class Payday:

    @classmethod
    def start(cls, public_log=''):
        """Try to start a new Payday.

        If there is a Payday that hasn't finished yet, then we work on it some
        more. We use the start time of that Payday to synchronize our work.

        """
        d = cls.db.one("""
            INSERT INTO paydays
                        (id, public_log, ts_start)
                 VALUES ( COALESCE((
                              SELECT id
                                FROM paydays
                               WHERE ts_end > ts_start
                                 AND stage IS NULL
                            ORDER BY id DESC LIMIT 1
                          ), 0) + 1
                        , %s
                        , now()
                        )
            ON CONFLICT (id) DO UPDATE
                    SET ts_start = COALESCE(paydays.ts_start, excluded.ts_start)
              RETURNING id, ts_start, ts_end, stage
        """, (public_log,), back_as=dict)
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
        log("Running payday #%(id)s, started at %(ts_start)s." % self.__dict__)

        self.shuffle(log_dir)

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
        self.stage = None

    def shuffle(self, log_dir='.'):
        if self.stage > 2:
            return
        get_transfers = lambda: self.db.all("""
            SELECT t.*
              FROM payday_transfers t
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
                self.transfer_virtually(cursor, self.ts_start, self.id)
                cursor.run("""
                    UPDATE paydays
                       SET nparticipants = (SELECT count(*) FROM payday_participants)
                     WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz;
                """)
                self.mark_stage_done(cursor)
            self.clean_up()
            transfers = get_transfers()

        self.transfer_for_real(transfers)

        self.db.self_check()
        self.end()
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
                 , goal
                 , kind
                 , main_currency
                 , accepted_currencies
                 , empty_currency_basket() AS leftover
              FROM participants p
             WHERE join_time < %(ts_start)s
               AND is_suspended IS NOT true
               AND status <> 'stub'
          ORDER BY join_time;

        CREATE UNIQUE INDEX ON payday_participants (id);

        CREATE TEMPORARY TABLE payday_tips ON COMMIT DROP AS
            SELECT t.id, t.tipper, t.tippee, t.amount, (p2.kind = 'group') AS to_team
                 , coalesce_currency_amount(t.paid_in_advance, t.amount::currency) AS paid_in_advance
              FROM ( SELECT DISTINCT ON (tipper, tippee) *
                       FROM tips
                      WHERE mtime < %(ts_start)s
                   ORDER BY tipper, tippee, mtime DESC
                   ) t
              JOIN payday_participants p ON p.id = t.tipper
              JOIN payday_participants p2 ON p2.id = t.tippee
             WHERE (p2.goal IS NULL OR p2.goal >= 0 OR t.paid_in_advance > 0)
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
             WHERE t.team IN (SELECT id FROM payday_participants)
               AND t.member IN (SELECT id FROM payday_participants);

        CREATE UNIQUE INDEX ON payday_takes (team, member);

        DROP TABLE IF EXISTS payday_transfers;
        CREATE TABLE payday_transfers
        ( id serial
        , tipper bigint
        , tippee bigint
        , amount currency_amount CHECK (amount >= 0)
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
                tip payday_tips;
                transfer_amount currency_amount;
            BEGIN
                IF (a_amount = 0) THEN RETURN; END IF;
                tip := (
                    SELECT t
                      FROM payday_tips t
                     WHERE t.tipper = a_tipper
                       AND t.tippee = COALESCE(a_team, a_tippee)
                );
                IF (tip IS NULL) THEN
                    RAISE 'tip not found: %%, %%, %%', a_tipper, a_tippee, a_team;
                END IF;
                IF (tip.paid_in_advance >= a_amount) THEN
                    transfer_amount := a_amount;
                ELSE
                    transfer_amount := tip.paid_in_advance;
                END IF;
                INSERT INTO payday_transfers
                            (tipper, tippee, amount, context, team, invoice)
                     VALUES (a_tipper, a_tippee, transfer_amount, a_context, a_team, a_invoice);
            END;
        $$ LANGUAGE plpgsql;


        -- Create a function to check whether a tip is "funded" or not

        CREATE OR REPLACE FUNCTION compute_tip_funding(tip payday_tips)
        RETURNS currency_amount AS $$
            DECLARE
                available_amount currency_amount;
            BEGIN
                available_amount := tip.paid_in_advance;
                IF (available_amount < 0) THEN
                    available_amount := zero(available_amount);
                END IF;
                RETURN available_amount;
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
                            AND compute_tip_funding(t) >= t.amount
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
                WITH updated_rows AS (
                     UPDATE payday_tips AS t
                        SET is_funded = false
                      WHERE is_funded IS NULL
                        AND to_team IS NOT true
                  RETURNING id, transfer(tipper, tippee, compute_tip_funding(t), 'partial-tip', NULL, NULL)
                )
                SELECT count(*) FROM updated_rows INTO count;
            END;
        $$ LANGUAGE plpgsql;

        """, dict(ts_start=ts_start))
        log("Prepared the DB.")

    @staticmethod
    def transfer_virtually(cursor, ts_start, payday_id):
        cursor.run("SELECT settle_tip_graph();")
        teams = cursor.all("""
            SELECT id, main_currency FROM payday_participants WHERE kind = 'group';
        """)
        for team_id, currency in teams:
            Payday.transfer_takes(cursor, team_id, currency, payday_id)
        cursor.run("""
            SELECT settle_tip_graph();
            UPDATE payday_tips SET is_funded = false WHERE is_funded IS NULL;
        """)

    @staticmethod
    def transfer_takes(cursor, team_id, currency, payday_id):
        """Resolve and transfer takes for the specified team
        """
        args = dict(team_id=team_id)
        tips = cursor.all("""
            UPDATE payday_tips AS t
               SET is_funded = compute_tip_funding(t) >= t.amount
             WHERE tippee = %(team_id)s
               AND compute_tip_funding(t) > 0
         RETURNING t.id, t.tipper, t.amount AS full_amount, t.paid_in_advance
                 , coalesce_currency_amount((
                       SELECT sum(tr.amount, t.amount::currency)
                         FROM transfers tr
                        WHERE tr.tipper = t.tipper
                          AND tr.team = %(team_id)s
                          AND tr.context IN ('take', 'partial-take', 'leftover-take')
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
        transfers, leftover = Payday.resolve_takes(tips, takes, currency, payday_id)
        for t in transfers:
            context = 'leftover-take' if t.is_leftover else 'partial-take' if t.is_partial else 'take'
            cursor.run("SELECT transfer(%s, %s, %s, %s, %s, NULL)",
                       (t.tipper, t.member, t.amount, context, team_id))
        cursor.run("UPDATE payday_participants SET leftover = %s WHERE id = %s",
                   (leftover, team_id))

    @staticmethod
    def resolve_takes(tips, takes, ref_currency, payday_id):
        """Resolve many-to-many donations (team takes)
        """
        for tip in tips:
            if tip.paid_in_advance is None:
                tip.paid_in_advance = tip.full_amount.zero()
            tip.funded_amount = min(tip.full_amount, tip.paid_in_advance)
            tip.is_partial = tip.funded_amount < tip.full_amount
        total_income = MoneyBasket(t.funded_amount for t in tips)
        if total_income == 0:
            return (), total_income
        takes = [t for t in takes if not (t.paid_in_advance and t.paid_in_advance < 0)]
        leftover_takes = [t for t in takes if t.paid_in_advance and not t.amount]
        takes = [t for t in takes if t.amount and t.paid_in_advance]
        if not (takes or leftover_takes):
            return (), total_income
        fuzzy_income_sum = total_income.fuzzy_sum(ref_currency)
        manual_takes = [t for t in takes if t.amount > 0]
        if manual_takes:
            manual_takes_sum = MoneyBasket(t.amount for t in manual_takes)
            n_auto_takes = sum(1 for t in takes if t.amount < 0) or 1
            auto_take = (
                (fuzzy_income_sum - manual_takes_sum.fuzzy_sum(ref_currency)) /
                n_auto_takes
            ).round_up()
            if auto_take < 0:
                auto_take = auto_take.zero()
        else:
            auto_take = fuzzy_income_sum
        for take in takes:
            if take.paid_in_advance is None:
                take.paid_in_advance = take.amount.zero()
            if take.amount < 0:
                take.amount = auto_take.convert(take.amount.currency)
                take.max_amount = take.paid_in_advance
            else:
                take.max_amount = min(take.amount, take.paid_in_advance)
            assert take.amount >= 0
        tip_currencies = set(t.full_amount.currency for t in tips)
        takes_by_preferred_currency = group_by(takes, lambda t: t.main_currency)
        takes_by_secondary_currency = {c: [] for c in tip_currencies}
        resolved_takes = resolve_amounts(
            fuzzy_income_sum,
            {take.member: take.amount.convert(ref_currency) for take in takes},
            maximum_amounts={
                take.member: take.max_amount.convert(ref_currency)
                for take in takes
            },
            payday_id=payday_id,
        )
        for take in takes:
            take.amount = resolved_takes.get(take.member) or take.amount.zero()
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
        fuzzy_takes_sum = MoneyBasket(t.amount for t in takes).fuzzy_sum(ref_currency)
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
                    tip.amount = (tip.funded_amount * tip.ratio).round_up()
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
                                min_tip_amount = (tip.funded_amount * min_tip_ratio).round_up()
                                tip.leeway = min_tip_amount - tip.amount
                            else:
                                tip.leeway = tip.amount.zero()
                    else:
                        # The naive amounts are too low: we can raise all the
                        # tips that aren't already at their maximum
                        for tip in tips:
                            tip.leeway = tip.funded_amount - tip.amount
                    leeway = MoneyBasket(tip.leeway for tip in tips).fuzzy_sum(ref_currency)
                    if leeway == 0:
                        # We don't actually have any leeway, give up
                        adjust_tips = False
                    else:
                        leeway_ratio = min(delta / leeway, 1)
        if adjust_tips:
            tips.sort(key=lambda tip: (-tip.weeks_to_catch_up, tip.id))
        else:
            tips.sort(key=attrgetter('id'))
        # Loop: compute the adjusted donation amounts, and do the transfers
        transfers = {}
        for tip in tips:
            tip_currency = tip.full_amount.currency
            if adjust_tips:
                tip_amount = (tip.amount + tip.leeway * leeway_ratio).round_up()
                if tip_amount == 0:
                    continue
                assert tip_amount > 0
            else:
                tip_amount = (tip.funded_amount * tips_ratio).round_up()
            tip.amount = min(tip_amount, tip.funded_amount)
            sorted_takes = chain(
                takes_by_preferred_currency.get(tip_currency, ()),
                takes_by_secondary_currency.get(tip_currency, ()),
                takes
            )
            for take in sorted_takes:
                if take.amount == 0 or tip.tipper == take.member:
                    continue
                fuzzy_take_amount = take.amount.convert(tip_currency)
                transfer_amount = min(
                    tip.amount,
                    fuzzy_take_amount,
                    max(tip.paid_in_advance, 0),
                    max(take.paid_in_advance.convert(tip_currency), 0),
                )
                if transfer_amount == 0:
                    continue
                transfer_key = (tip.tipper, take.member)
                if transfer_key in transfers:
                    transfers[transfer_key].amount += transfer_amount
                else:
                    transfers[transfer_key] = TakeTransfer(
                        tip.tipper, take.member, transfer_amount,
                        is_partial=tip.is_partial,
                    )
                if transfer_amount == fuzzy_take_amount:
                    take.amount = take.amount.zero()
                else:
                    take.amount -= transfer_amount.convert(take.amount.currency)
                tip.paid_in_advance -= transfer_amount
                take.paid_in_advance -= transfer_amount.convert(take.paid_in_advance.currency)
                tip.amount -= transfer_amount
                tip.funded_amount -= transfer_amount
                if tip.amount == 0:
                    break
        # Try to use the leftover to reduce the advances received in the past by
        # members who have now left the team or have zeroed takes.
        transfers = list(transfers.values())
        leftover = total_income - MoneyBasket(t.amount for t in transfers)
        assert leftover >= 0, "leftover is negative"
        if leftover and leftover_takes:
            leftover_takes.sort(key=lambda t: t.member)
            leftover_takes_fuzzy_sum = MoneyBasket(
                take.paid_in_advance for take in leftover_takes
            ).fuzzy_sum(ref_currency)
            advance_ratio = leftover.fuzzy_sum(ref_currency) / leftover_takes_fuzzy_sum
            leftover_transfers = {}
            for take in leftover_takes:
                take.amount = (take.paid_in_advance * advance_ratio).round()
                for tip in tips:
                    if tip.funded_amount == 0 or tip.tipper == take.member:
                        continue
                    tip_currency = tip.full_amount.currency
                    fuzzy_take_amount = take.amount.convert(tip_currency)
                    transfer_amount = min(
                        tip.funded_amount,
                        fuzzy_take_amount,
                        max(tip.paid_in_advance, 0),
                        max(take.paid_in_advance.convert(tip_currency), 0),
                    )
                    if transfer_amount == 0:
                        continue
                    transfer_key = (tip.tipper, take.member)
                    assert transfer_key not in leftover_transfers
                    leftover_transfers[transfer_key] = TakeTransfer(
                        tip.tipper, take.member, transfer_amount,
                        is_leftover=True, is_partial=tip.is_partial,
                    )
                    if transfer_amount == fuzzy_take_amount:
                        take.amount = take.amount.zero()
                    else:
                        take.amount -= transfer_amount.convert(take.amount.currency)
                    tip.paid_in_advance -= transfer_amount
                    take.paid_in_advance -= transfer_amount.convert(take.paid_in_advance.currency)
                    tip.funded_amount -= transfer_amount
                    if take.amount == 0:
                        break
            transfers.extend(leftover_transfers.values())
        return transfers, leftover

    def transfer_for_real(self, transfers):
        print("Starting transfers (n=%i)" % len(transfers))
        for t in transfers:
            self.record_transfer(t)

    def record_transfer(self, t):
        log(f"Recording transfer #{t.id} (amount={t.amount} context={t.context} team={t.team})")
        with self.db.get_cursor() as cursor:
            cursor.run("""
                INSERT INTO transfers
                            (tipper, tippee, amount, context,
                             team, invoice, status,
                             wallet_from, wallet_to, virtual)
                     VALUES (%(tipper)s, %(tippee)s, %(amount)s, %(context)s,
                             %(team)s, %(invoice)s, 'succeeded',
                             'x', 'y', true);

                WITH latest_tip AS (
                         SELECT *
                           FROM tips
                          WHERE tipper = %(tipper)s
                            AND tippee = coalesce(%(team)s, %(tippee)s)
                       ORDER BY mtime DESC
                          LIMIT 1
                     )
                UPDATE tips t
                   SET paid_in_advance = (t.paid_in_advance - %(amount)s)
                  FROM latest_tip lt
                 WHERE t.tipper = lt.tipper
                   AND t.tippee = lt.tippee
                   AND t.mtime >= lt.mtime;
            """, t.__dict__)
            if t.team:
                cursor.run("""
                    WITH latest_take AS (
                             SELECT t.*
                               FROM takes t
                              WHERE t.team = %(team)s
                                AND t.member = %(tippee)s
                                AND t.amount IS NOT NULL
                           ORDER BY t.mtime DESC
                              LIMIT 1
                         )
                    UPDATE takes t
                       SET paid_in_advance = (
                               coalesce_currency_amount(lt.paid_in_advance, lt.amount::currency) -
                               convert(%(amount)s, lt.amount::currency)
                           )
                      FROM latest_take lt
                     WHERE t.team = lt.team
                       AND t.member = lt.member
                       AND t.mtime >= lt.mtime;
                """, t.__dict__)

    @classmethod
    def clean_up(cls):
        cls.db.run("""
            DROP FUNCTION settle_tip_graph();
            DROP FUNCTION transfer(bigint, bigint, currency_amount, transfer_context, bigint, int);
        """)

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
                        AND ( context IN ('tip', 'take') OR
                              context IN ('partial-tip', 'partial-take', 'leftover-take') AND
                              %(ts_start)s >= '2021-02-19'
                            )
                 )
               , our_tips AS (
                     SELECT *
                       FROM our_transfers
                      WHERE team IS NULL
                 )
               , our_takes AS (
                     SELECT *
                       FROM our_transfers
                      WHERE team IS NOT NULL
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
                          AND p.is_suspended IS NOT true
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
            payday_id = cursor.one("""
                SELECT id
                  FROM paydays
                 WHERE ts_start IS NOT NULL
              ORDER BY id DESC
                 LIMIT 1
            """, default=0) + 1
            cls.prepare(cursor, now)
            cls.transfer_virtually(cursor, now, payday_id)
            cursor.run("""
            CREATE INDEX ON payday_transfers (tippee);
            CREATE INDEX ON payday_transfers (team) WHERE team IS NOT NULL;
            """)
            cursor.run("""
            UPDATE tips t
               SET is_funded = t2.is_funded
              FROM payday_tips t2
             WHERE t.id = t2.id
               AND t.is_funded <> t2.is_funded;
            """)
            cursor.run("""
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
            """)
            cursor.run("""
            UPDATE participants p
               SET receiving = p2.receiving
                 , npatrons = p2.npatrons
              FROM ( SELECT p2.id
                          , count(*) AS npatrons
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
               AND p.npatrons <> p2.npatrons
               AND p.status = 'stub';
            """)
            cursor.run("""
            UPDATE takes t
               SET actual_amount = t2.actual_amount
              FROM ( SELECT t2.id
                          , (
                                SELECT basket_sum(tr.amount)
                                  FROM payday_transfers tr
                                 WHERE tr.team = t2.team
                                   AND tr.tippee = t2.member
                                   AND tr.context IN ('take', 'partial-take')
                            ) AS actual_amount
                       FROM current_takes t2
                   ) t2
             WHERE t.id = t2.id
               AND coalesce_currency_basket(t.actual_amount) <> t2.actual_amount;
            """)
            cursor.run("""
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
            """)
            cursor.run("""
            UPDATE participants p
               SET taking = p2.taking
              FROM ( SELECT p2.id
                          , coalesce_currency_amount((
                                SELECT sum(t.amount, p2.main_currency)
                                  FROM payday_transfers t
                                 WHERE t.tippee = p2.id
                                   AND context IN ('take', 'partial-take')
                            ), p2.main_currency) AS taking
                       FROM participants p2
                   ) p2
             WHERE p.id = p2.id
               AND p.taking <> p2.taking;
            """)
            cursor.run("""
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
            """)
            cursor.run("""
            UPDATE participants p
               SET leftover = p2.leftover
              FROM ( SELECT p2.id, p2.leftover
                       FROM payday_participants p2
                      WHERE p2.kind = 'group'
                   ) p2
             WHERE p.id = p2.id
               AND coalesce_currency_basket(p.leftover) <> p2.leftover;
            """)
            cursor.run("""
            UPDATE participants p
               SET nteampatrons = p2.nteampatrons
              FROM ( SELECT p2.id
                          , ( SELECT count(DISTINCT t.tipper)
                                FROM payday_transfers t
                               WHERE t.tippee = p2.id
                                 AND t.context IN ('take', 'partial-take')
                            ) AS nteampatrons
                       FROM participants p2
                      WHERE p2.status <> 'stub'
                        AND p2.kind IN ('individual', 'organization')
                   ) p2
             WHERE p.id = p2.id
               AND p.nteampatrons <> p2.nteampatrons;
            """)
            cursor.run("""
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
        if self.stage == 3:
            self.generate_income_notifications()
            self.mark_stage_done()
        if self.stage == 4:
            from liberapay.payin.cron import send_donation_reminder_notifications
            send_donation_reminder_notifications()
            self.mark_stage_done()
        if self.stage == 5:
            self.generate_payment_account_required_notifications()
            self.mark_stage_done()

    def generate_income_notifications(self):
        previous_ts_end = self.db.one("""
            SELECT ts_end
              FROM paydays
             WHERE ts_start < %s
          ORDER BY ts_end DESC
             LIMIT 1
        """, (self.ts_start,), default=constants.BIRTHDAY)
        n = 0
        r = self.db.all("""
            SELECT tippee, json_agg(t) AS transfers
              FROM transfers t
             WHERE "timestamp" > %(previous_ts_end)s
               AND "timestamp" <= %(ts_end)s
               AND context IN ('tip', 'take', 'partial-take', 'final-gift')
               AND status = 'succeeded'
               AND NOT EXISTS (
                       SELECT 1
                         FROM notifications n
                        WHERE n.participant = tippee
                          AND n.event LIKE 'income~%%'
                          AND n.ts > %(ts_end)s
                   )
          GROUP BY tippee
          ORDER BY tippee
        """, dict(previous_ts_end=previous_ts_end, ts_end=self.ts_end))
        for tippee_id, transfers in r:
            p = self.db.Participant.from_id(tippee_id)
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
            team_names = {t.id: t.username for t in teams}
            get_username = lambda i: team_names.get(i) or self.db.one(
                "SELECT username FROM participants WHERE id = %s", (i,)
            )
            by_team = {get_username(t_id): by_team.get(t_id, nothing) for t_id in team_ids}
            notif_id = p.notify(
                'income~v2',
                total=total.fuzzy_sum(p.main_currency),
                personal=personal,
                personal_npatrons=personal_npatrons,
                by_team=by_team,
                web=False,
            )
            if notif_id:
                n += 1
        log(f"Sent {n} income notifications (out of {len(r)} tippees).")

    def generate_payment_account_required_notifications(self):
        n = 0
        participants = self.db.all("""
            SELECT p
              FROM participants p
             WHERE p.payment_providers = 0
               AND p.status = 'active'
               AND p.kind IN ('individual', 'organization')
               AND (p.goal IS NULL OR p.goal >= 0)
               AND p.is_suspended IS NOT true
               AND ( EXISTS (
                       SELECT 1
                         FROM current_tips t
                         JOIN participants tipper ON tipper.id = t.tipper
                        WHERE t.tippee = p.id
                          AND t.amount > 0
                          AND t.renewal_mode > 0
                          AND (t.paid_in_advance IS NULL OR t.paid_in_advance < t.amount)
                          AND tipper.email IS NOT NULL
                          AND tipper.is_suspended IS NOT true
                          AND tipper.status = 'active'
                          AND t.mtime > (current_timestamp - interval '1 year')
                   ) OR EXISTS (
                       SELECT 1
                         FROM current_takes take
                         JOIN participants team ON team.id = take.team
                        WHERE take.member = p.id
                          AND take.amount <> 0
                          AND team.receiving > 0
                   ) )
               AND NOT EXISTS (
                       SELECT 1
                         FROM notifications n
                        WHERE n.participant = p.id
                          AND n.event = 'payment_account_required'
                          AND n.ts > (current_timestamp - interval '6 months')
                   )
        """)
        for p in participants:
            p.notify('payment_account_required', force_email=True)
            n += 1
        log("Sent %i payment_account_required notifications." % n)


def compute_next_payday_date():
    today = pando.utils.utcnow().date()
    days_till_wednesday = (3 - today.isoweekday()) % 7
    if days_till_wednesday == 0:
        payday_is_already_done = website.db.one("""
            SELECT count(*) > 0
              FROM paydays
             WHERE ts_start::date = %s
               AND ts_end > ts_start
        """, (today,))
        if payday_is_already_done:
            days_till_wednesday = 7
    return today + timedelta(days=days_till_wednesday)


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
    next_payday_id = last_payday.id + 1 if last_payday else 1
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
        last_issue_payday_id = int(last_issue['title'].split()[-1].lstrip('#'))
        if last_issue_payday_id == next_payday_id:
            return  # already created
        assert last_issue_payday_id == last_payday.id
        next_issue['title'] = last_issue['title'].replace(
            str(last_issue_payday_id), str(next_payday_id)
        )
        next_issue['body'] = last_issue['body']
    else:
        next_issue['title'] = "Payday #%s" % next_payday_id
    next_issue = github.api_request(
        'POST', '', '/repos/%s/issues' % repo, json=next_issue, sess=sess
    ).json()
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
               AND stage IS NULL
        """)
        assert not r, "payday has already been run this week"

    # Prevent a race condition, by acquiring a DB lock
    with website.db.lock('payday', blocking=False):
        try:
            paypal.sync_all_pending_payments(website.db)
            Payday.start().run(website.env.log_dir, website.env.keep_payday_logs)
        except KeyboardInterrupt:  # pragma: no cover
            pass
        except Exception as e:  # pragma: no cover
            website.tell_sentry(e, allow_reraise=False)
            raise


if __name__ == '__main__':  # pragma: no cover
    main()
