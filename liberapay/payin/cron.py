from collections import defaultdict
from datetime import date
from operator import itemgetter
from time import sleep

from pando import json

from ..billing.payday import compute_next_payday_date
from ..cron import logger
from ..exceptions import (
    AccountSuspended, BadDonationCurrency, MissingPaymentAccount, NoSelfTipping,
    RecipientAccountSuspended, UserDoesntAcceptTips, NextAction,
)
from ..i18n.currencies import Money
from ..website import website
from ..utils import utcnow
from ..utils.types import Object
from .common import prepare_payin, resolve_tip
from .stripe import charge


def reschedule_renewals():
    """This function looks for inconsistencies in scheduled payins.
    """
    donors = website.db.all("""
        SELECT p, tips.count AS expected
          FROM ( SELECT tip.tipper, count(*)
                   FROM current_tips tip
                   JOIN participants tippee_p ON tippee_p.id = tip.tippee
                  WHERE tip.renewal_mode > 0
                    AND tip.paid_in_advance IS NOT NULL
                    AND tippee_p.status = 'active'
                    AND ( tippee_p.goal IS NULL OR tippee_p.goal >= 0 )
                    AND tippee_p.is_suspended IS NOT TRUE
                    AND tippee_p.payment_providers > 0
                    AND coalesce((
                            SELECT pt.status
                              FROM payin_transfers pt
                             WHERE pt.payer = tip.tipper
                               AND coalesce(pt.team, pt.recipient) = tip.tippee
                          ORDER BY pt.ctime DESC
                             LIMIT 1
                        ), 'succeeded') = 'succeeded'
                    AND ( tippee_p.kind <> 'group' OR EXISTS (
                            SELECT 1
                              FROM current_takes take
                              JOIN participants member_p ON member_p.id = take.member
                             WHERE take.team = tip.tippee
                               AND take.member <> tip.tipper
                               AND take.amount <> 0
                               AND member_p.is_suspended IS NOT TRUE
                               AND member_p.payment_providers > 0
                        ) )
               GROUP BY tip.tipper
               ) tips
          JOIN participants p ON p.id = tips.tipper
         WHERE p.status = 'active'
           AND p.is_suspended IS NOT true
           AND tips.count > coalesce((
                   SELECT sum(json_array_length(sp.transfers))
                     FROM scheduled_payins sp
                    WHERE sp.payer = p.id
                      AND sp.payin IS NULL
               ), 0)
    """)
    for p, expected in donors:
        logger.info(f"Rescheduling the renewals of participant ~{p.id}")
        new_schedule = p.schedule_renewals()
        actual = sum(len(sp.transfers) for sp in new_schedule)
        if actual < expected:
            logger.warning(
                "Rescheduling the renewals of participant ~%s failed to correct "
                "the imbalance: expected %s, found %s",
                p.id, expected, actual,
            )
        sleep(0.1)
    donors = website.db.all("""
        SELECT ( SELECT p FROM participants p WHERE p.id = tip.tipper )
          FROM current_tips tip
          JOIN participants tippee_p ON tippee_p.id = tip.tippee
         WHERE tip.renewal_mode = 2
           AND tippee_p.payment_providers & 1 = 1
           AND EXISTS (
                   SELECT 1
                     FROM scheduled_payins sp
                    WHERE sp.payer = tip.tipper
                      AND sp.automatic IS false
                      AND sp.payin IS NULL
                      AND EXISTS (
                              SELECT 1
                                FROM json_array_elements(sp.transfers)
                               WHERE value->>'tippee_id' = tip.tippee::text
                          )
               )
    """)
    for p in donors:
        logger.info(f"Rescheduling the renewals of participant ~{p.id}")
        p.schedule_renewals()
        sleep(0.1)


def send_donation_reminder_notifications():
    """This function reminds donors to renew their donations.

    The notifications are sent two weeks before the due date.
    """
    db = website.db
    counts = defaultdict(int)
    rows = db.all("""
        SELECT (SELECT p FROM participants p WHERE p.id = sp.payer) AS payer
             , json_agg((SELECT a FROM (
                   SELECT sp.id, sp.execution_date, sp.amount, sp.transfers
               ) a)) AS payins
          FROM scheduled_payins sp
     LEFT JOIN LATERAL (
                   SELECT pi.*
                     FROM payins pi
                    WHERE pi.payer = sp.payer
                      AND NOT pi.off_session
                 ORDER BY pi.ctime DESC
                    LIMIT 1
               ) last_payin ON true
         WHERE sp.execution_date <= (current_date + (CASE
                   WHEN last_payin.ctime >= (current_date - interval '14 days')
                   THEN interval '7 days'
                   ELSE interval '14 days'
               END))
           AND sp.automatic IS NOT true
           AND sp.payin IS NULL
           AND sp.ctime < (current_timestamp - interval '6 hours')
      GROUP BY sp.payer
        HAVING count(*) FILTER (
                   WHERE sp.notifs_count = 0
                      OR sp.notifs_count = 1 AND sp.last_notif_ts <= (current_date - interval '4 weeks')
                      OR sp.notifs_count = 2 AND sp.last_notif_ts <= (current_date - interval '26 weeks')
               ) > 0
      ORDER BY sp.payer
    """)
    today = utcnow().date()
    next_payday = compute_next_payday_date()
    for payer, payins in rows:
        if not payer.can_attempt_payment:
            continue
        payins.sort(key=itemgetter('execution_date'))
        _check_scheduled_payins(db, payer, payins, automatic=False)
        if not payins:
            continue
        donations = []
        overdue = False
        for sp in payins:
            for tr in sp['transfers']:
                if tr.get('impossible'):
                    continue
                tip = tr['tip']
                due_date = tip.compute_renewal_due_date(next_payday)
                donations.append({
                    'due_date': due_date,
                    'period': tip.period,
                    'periodic_amount': tip.periodic_amount,
                    'tippee_username': tr['tippee_username'],
                })
                if due_date <= today:
                    overdue = True
        if not donations:
            continue
        payer.notify(
            'donate_reminder~v2',
            donations=donations,
            overdue=overdue,
            email_unverified_address=True,
        )
        counts['donate_reminder'] += 1
        db.run("""
            UPDATE scheduled_payins
               SET notifs_count = notifs_count + 1
                 , last_notif_ts = now()
             WHERE payer = %s
               AND id IN %s
        """, (payer.id, tuple(sp['id'] for sp in payins)))
    for k, n in sorted(counts.items()):
        logger.info("Sent %i %s notifications." % (n, k))


def send_upcoming_debit_notifications():
    """This daily cron job notifies donors who are about to be debited.

    The notifications are sent at most once a month, 14 days before the first
    payment of the "month" (31 days, not the calendar month).
    """
    db = website.db
    counts = defaultdict(int)
    rows = db.all("""
        SELECT (SELECT p FROM participants p WHERE p.id = sp.payer) AS payer
             , json_agg((SELECT a FROM (
                   SELECT sp.id, sp.execution_date, sp.amount, sp.transfers
               ) a)) AS payins
          FROM scheduled_payins sp
         WHERE sp.execution_date <= (current_date + interval '45 days')
           AND sp.automatic
           AND sp.notifs_count = 0
           AND sp.payin IS NULL
           AND sp.ctime < (current_timestamp - interval '6 hours')
      GROUP BY sp.payer, (sp.amount).currency
        HAVING min(sp.execution_date) <= (current_date + interval '14 days')
      ORDER BY sp.payer, (sp.amount).currency
    """)
    for payer, payins in rows:
        if not payer.can_attempt_payment:
            continue
        _check_scheduled_payins(db, payer, payins, automatic=True)
        if not payins:
            continue
        payins.sort(key=itemgetter('execution_date'))
        context = {
            'payins': payins,
            'total_amount': sum(sp['amount'] for sp in payins),
        }
        for sp in context['payins']:
            for tr in sp['transfers']:
                del tr['tip'], tr['beneficiary']
        if len(payins) > 1:
            last_execution_date = payins[-1]['execution_date']
            max_execution_date = max(sp['execution_date'] for sp in payins)
            assert last_execution_date == max_execution_date
            context['ndays'] = (max_execution_date - utcnow().date()).days
        currency = payins[0]['amount'].currency
        while True:
            route = db.one("""
                SELECT r
                  FROM exchange_routes r
                 WHERE r.participant = %s
                   AND r.status = 'chargeable'
                   AND r.network::text LIKE 'stripe-%%'
              ORDER BY r.is_default_for = %s DESC NULLS LAST
                     , r.is_default NULLS LAST
                     , r.network = 'stripe-sdd' DESC
                     , r.ctime DESC
                 LIMIT 1
            """, (payer.id, currency))
            if route is None:
                break
            route.sync_status()
            if route.status == 'chargeable':
                break
        if route:
            event = 'upcoming_debit'
            context['instrument_brand'] = route.get_brand()
            context['instrument_partial_number'] = route.get_partial_number()
        else:
            event = 'missing_route'
        payer.notify(event, email_unverified_address=True, **context)
        counts[event] += 1
        db.run("""
            UPDATE scheduled_payins
               SET notifs_count = notifs_count + 1
                 , last_notif_ts = now()
             WHERE payer = %s
               AND id IN %s
        """, (payer.id, tuple(sp['id'] for sp in payins)))
    for k, n in sorted(counts.items()):
        logger.info("Sent %i %s notifications." % (n, k))


def execute_scheduled_payins():
    """This daily cron job initiates scheduled payments.
    """
    db = website.db
    counts = defaultdict(int)
    retry = False
    rows = db.all("""
        SELECT p AS payer, json_agg(json_build_object(
                   'id', sp.id,
                   'execution_date', sp.execution_date,
                   'transfers', sp.transfers,
                   'route', r.id
               )) AS scheduled_payins
          FROM scheduled_payins sp
          JOIN participants p ON p.id = sp.payer
          JOIN LATERAL (
                 SELECT r.*
                   FROM exchange_routes r
                  WHERE r.participant = sp.payer
                    AND r.status = 'chargeable'
                    AND r.network::text LIKE 'stripe-%%'
                    AND ( sp.amount::currency = 'EUR' OR r.network <> 'stripe-sdd' )
               ORDER BY r.is_default_for = sp.amount::currency DESC NULLS LAST
                      , r.is_default DESC NULLS LAST
                      , r.ctime DESC
                  LIMIT 1
               ) r ON true
         WHERE ( r.network = 'stripe-sdd' AND sp.execution_date <= (current_date + interval '6 days') OR
                 r.network = 'stripe-card' AND sp.execution_date <= current_date )
           AND sp.last_notif_ts < (current_date - interval '2 days')
           AND sp.automatic
           AND sp.payin IS NULL
           AND p.is_suspended IS NOT TRUE
      GROUP BY p.id
      ORDER BY p.id
    """)
    for payer, scheduled_payins in rows:
        scheduled_payins[:] = [Object(**sp) for sp in scheduled_payins]
        for sp in scheduled_payins:
            sp.route = db.ExchangeRoute.from_id(payer, sp.route)
            sp.route.sync_status()
            if sp.route.status != 'chargeable':
                retry = True
                scheduled_payins.remove(sp)

    def unpack():
        for payer, scheduled_payins in rows:
            last = len(scheduled_payins)
            for i, sp in enumerate(scheduled_payins, 1):
                yield sp.id, sp.execution_date, sp.transfers, payer, sp.route, i == last

    for sp_id, execution_date, transfers, payer, route, update_donor in unpack():
        transfers, canceled, impossible, actionable = _filter_transfers(
            payer, transfers, automatic=True
        )
        if transfers:
            payin_amount = sum(tr['amount'] for tr in transfers)
            proto_transfers = []
            sepa_only = len(transfers) > 1
            for tr in list(transfers):
                try:
                    proto_transfers.extend(resolve_tip(
                        db, tr['tip'], tr['beneficiary'], 'stripe',
                        payer, route.country, tr['amount'],
                        sepa_only=sepa_only,
                    ))
                except (
                    MissingPaymentAccount,
                    NoSelfTipping,
                    RecipientAccountSuspended,
                    UserDoesntAcceptTips,
                ):
                    impossible.append(tr)
                    transfers.remove(tr)
                    payin_amount -= tr['amount']
                except BadDonationCurrency:
                    actionable.append(tr)
                    transfers.remove(tr)
                    payin_amount -= tr['amount']
        if transfers:
            try:
                payin = prepare_payin(
                    db, payer, payin_amount, route, proto_transfers,
                    off_session=True,
                )[0]
            except AccountSuspended:
                continue
            db.run("""
                UPDATE scheduled_payins
                   SET payin = %s
                     , mtime = current_timestamp
                 WHERE id = %s
            """, (payin.id, sp_id))
            try:
                payin = charge(db, payin, payer, route, update_donor=update_donor)
            except NextAction:
                payer.notify(
                    'renewal_unauthorized',
                    payin_id=payin.id, payin_amount=payin.amount,
                    provider='stripe',
                    email_unverified_address=True,
                    force_email=True,
                )
                counts['renewal_unauthorized'] += 1
                continue
            if payin.status == 'failed' and route.status == 'expired':
                can_retry = db.one("""
                    SELECT count(*) > 0
                      FROM exchange_routes
                     WHERE participant = sp.payer
                       AND status = 'chargeable'
                       AND network::text LIKE 'stripe-%%'
                       AND ( %s OR network <> 'stripe-sdd' )
                """, (payin.currency == 'EUR',))
                if can_retry:
                    retry = True
                    continue
            if payin.status in ('failed', 'succeeded'):
                payer.notify(
                    'payin_' + payin.status,
                    payin=payin._asdict(),
                    provider='Stripe',
                    email_unverified_address=True,
                )
                counts['payin_' + payin.status] += 1
        elif actionable:
            db.run("""
                UPDATE scheduled_payins
                   SET notifs_count = notifs_count + 1
                     , last_notif_ts = now()
                 WHERE payer = %s
                   AND id = %s
            """, (payer.id, sp_id))
        else:
            db.run("DELETE FROM scheduled_payins WHERE id = %s", (sp_id,))
        if actionable:
            for tr in actionable:
                tr['execution_date'] = execution_date
                del tr['beneficiary'], tr['tip']
            payer.notify(
                'renewal_actionable',
                transfers=actionable,
                email_unverified_address=True,
                force_email=True,
            )
            counts['renewal_actionable'] += 1
        if impossible:
            for tr in impossible:
                tr['execution_date'] = execution_date
                del tr['beneficiary'], tr['tip']
            payer.notify(
                'renewal_aborted',
                transfers=impossible,
                email_unverified_address=True,
            )
            counts['renewal_aborted'] += 1
    for k, n in sorted(counts.items()):
        logger.info("Sent %i %s notifications." % (n, k))
    if retry:
        execute_scheduled_payins()


def _check_scheduled_payins(db, payer, payins, automatic):
    """Check scheduled payins before they're acted upon.

    A scheduled payin can be out of sync with the state of the donor's tips or
    the status of the recipient's account if the `Participant.schedule_renewals()`
    method wasn't successfully called.
    """
    reschedule = False
    for sp in list(payins):
        if isinstance(sp['amount'], dict):
            sp['amount'] = Money(**sp['amount'])
        sp['execution_date'] = date(*map(int, sp['execution_date'].split('-')))
        canceled, impossible, actionable = _filter_transfers(
            payer, sp['transfers'], automatic
        )[1:]
        if canceled:
            if len(canceled) == len(sp['transfers']):
                payins.remove(sp)
                db.run("DELETE FROM scheduled_payins WHERE id = %(id)s", sp)
            else:
                old_tippee_ids = set(tr['tippee_id'] for tr in canceled)
                sp['transfers'] = [
                    tr for tr in sp['transfers'] if tr['tippee_id'] not in old_tippee_ids
                ]
                sp['amount'] = sum(tr['amount'] for tr in sp['transfers'])
                db.run("""
                    UPDATE scheduled_payins
                       SET amount = %(amount)s
                         , transfers = %(transfers)s
                         , mtime = current_timestamp
                     WHERE id = %(id)s
                """, dict(sp, transfers=json.dumps([
                    {k: v for k, v in tr.items() if k not in ('tip', 'beneficiary')}
                    for tr in sp['transfers']
                ])))
        for tr in impossible:
            tr['impossible'] = True
        if actionable:
            reschedule = True
            if len(actionable) == len(sp['transfers']):
                payins.remove(sp)
    if reschedule:
        payer.schedule_renewals()


def _filter_transfers(payer, transfers, automatic):
    """Splits scheduled transfers into 4 lists: okay, canceled, impossible, actionable.
    """
    if not payer.can_attempt_payment:
        return [], list(transfers), [], []
    canceled_transfers = []
    impossible_transfers = []
    actionable_transfers = []
    okay_transfers = []
    has_pending_transfer = set(website.db.all("""
        SELECT DISTINCT coalesce(pt.team, pt.recipient) AS tippee
          FROM payin_transfers pt
          JOIN payins pi ON pi.id = pt.payin
         WHERE pt.payer = %s
           AND ( pi.status IN ('awaiting_review', 'pending') OR
                 pt.status IN ('awaiting_review', 'pending') )
    """, (payer.id,)))
    for tr in transfers:
        if isinstance(tr['amount'], dict):
            tr['amount'] = Money(**tr['amount'])
        beneficiary = tr['beneficiary'] = website.db.Participant.from_id(tr['tippee_id'])
        tip = tr['tip'] = payer.get_tip_to(beneficiary)
        if tip.renewal_mode < 1 or automatic and (tip.renewal_mode != 2) or \
           beneficiary.id in has_pending_transfer:
            canceled_transfers.append(tr)
        elif beneficiary.status != 'active' or beneficiary.is_suspended or \
             not beneficiary.accepts_tips or \
             beneficiary.payment_providers == 0:
            impossible_transfers.append(tr)
        elif automatic and \
             (tip.amount.currency not in beneficiary.accepted_currencies_set or
              beneficiary.payment_providers & 1 == 0):
            actionable_transfers.append(tr)
        else:
            okay_transfers.append(tr)
    return okay_transfers, canceled_transfers, impossible_transfers, actionable_transfers


def execute_reviewed_payins():
    """Submit or cancel payins which have been held up for review.
    """
    payins = website.db.all("""
        SELECT pi, payer_p, r
          FROM payins pi
          JOIN participants payer_p ON payer_p.id = pi.payer
          JOIN exchange_routes r ON r.id = pi.route
         WHERE pi.status = 'awaiting_review'
           AND ( payer_p.is_suspended IS FALSE OR NOT EXISTS (
                   SELECT 1
                     FROM payin_transfers pt
                     JOIN participants recipient_p ON recipient_p.id = pt.recipient
                    WHERE pt.payin = pi.id
                      AND recipient_p.join_time::date::text >= '2022-12-23'
                      AND ( recipient_p.marked_as IS NULL OR
                            ( SELECT max(e.ts)
                                FROM events e
                               WHERE e.participant = pt.recipient
                                 AND e.type = 'flags_changed'
                            ) > (current_timestamp - interval '6 hours')
                          )
               ) )
    """)
    for payin, payer, route in payins:
        route.__dict__['participant'] = payer
        charge(website.db, payin, payer, route)
