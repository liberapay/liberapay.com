from collections import defaultdict
from datetime import date

from pando import json

from ..cron import logger
from ..i18n.currencies import Money
from ..website import website
from ..utils import utcnow
from .common import prepare_donation, prepare_payin
from .stripe import charge


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
               ) a ORDER BY a.execution_date)) AS payins
          FROM scheduled_payins sp
         WHERE sp.execution_date <= (current_date + interval '45 days')
           AND sp.automatic
           AND sp.notifs_count = 0
      GROUP BY sp.payer, (sp.amount).currency
        HAVING min(sp.execution_date) <= (current_date + interval '14 days')
    """)
    for payer, payins in rows:
        if payer.is_suspended:
            continue
        route = db.one("""
            SELECT r
              FROM exchange_routes r
             WHERE r.participant = %s
               AND r.status = 'chargeable'
               AND r.network::text LIKE 'stripe-%%'
          ORDER BY r.is_default NULLS LAST
                 , r.network = 'stripe-sdd' DESC
                 , r.ctime DESC
             LIMIT 1
        """, (payer.id,))
        for sp in list(payins):
            sp['amount'] = Money(**sp['amount'])
            sp['execution_date'] = date(*map(int, sp['execution_date'].split('-')))
            canceled, impossible = _filter_transfers(payer, sp['transfers'])[1:]
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
                         WHERE id = %(id)s
                    """, dict(sp, transfers=json.dumps([
                        {k: v for k, v in tr.items() if k not in ('tip', 'beneficiary')}
                        for tr in sp['transfers']
                    ])))
            for tr in impossible:
                tr['impossible'] = True
        if not payins:
            continue
        context = {
            'payins': payins,
            'total_amount': sum(sp['amount'] for sp in payins),
        }
        for sp in context['payins']:
            for tr in sp['transfers']:
                del tr['tip'], tr['beneficiary']
        if len(payins) > 1:
            context['ndays'] = (payins[-1]['execution_date'] - utcnow().date()).days
        if route:
            event = 'upcoming_debit'
            context['instrument_brand'] = route.get_brand()
            context['instrument_partial_number'] = route.get_partial_number()
            if route.network == 'stripe-sdd':
                source = route.stripe_source
                context.update({
                    'creditor_identifier': website.app_conf.sepa_creditor_identifier,
                    'mandate_creation_date': route.ctime.date(),
                    'mandate_id': source.sepa_debit.mandate_reference,
                    'mandate_url': source.sepa_debit.mandate_url,
                })
        else:
            event = 'missing_route'
        payer.notify(event, **context)
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
    rows = db.all("""
        SELECT sp.id, sp.execution_date, sp.transfers
             , p AS payer, r.*::exchange_routes AS route
          FROM scheduled_payins sp
          JOIN participants p ON p.id = sp.payer
          JOIN LATERAL (
                 SELECT r.*
                   FROM exchange_routes r
                  WHERE r.participant = sp.payer
                    AND r.status = 'chargeable'
                    AND r.network::text LIKE 'stripe-%%'
               ORDER BY r.is_default NULLS LAST
                      , r.network = 'stripe-sdd' DESC
                      , r.ctime DESC
                  LIMIT 1
               ) r ON true
         WHERE ( r.network = 'stripe-sdd' AND sp.execution_date = (current_date + interval '5 days') OR
                 r.network = 'stripe-card' AND sp.execution_date = current_date )
           AND sp.last_notif_ts < (current_date - interval '2 days')
           AND sp.automatic
           AND p.is_suspended IS NOT TRUE
    """)
    for sp_id, execution_date, transfers, payer, route in rows:
        route.__dict__['participant'] = payer
        transfers, canceled, impossible = _filter_transfers(payer, transfers)
        if impossible:
            for tr in impossible:
                tr['execution_date'] = execution_date
                del tr['beneficiary'], tr['tip']
            payer.notify('renewal_aborted', transfers=impossible)
            counts['renewal_aborted'] += 1
        if transfers:
            payin_amount = sum(tr['amount'] for tr in transfers)
            payin = prepare_payin(db, payer, payin_amount, route, off_session=True)
            for tr in transfers:
                prepare_donation(
                    db, payin, tr['tip'], tr['beneficiary'], 'stripe',
                    payer, route.country, tr['amount']
                )
            payin = charge(db, payin, payer)
            if payin.status in ('failed', 'succeeded'):
                payer.notify('payin_' + payin.status, payin=payin._asdict(), provider='Stripe')
                counts['payin_' + payin.status] += 1
        db.run("DELETE FROM scheduled_payins WHERE id = %s", (sp_id,))
    for k, n in sorted(counts.items()):
        logger.info("Sent %i %s notifications." % (n, k))


def _filter_transfers(payer, transfers):
    """Splits scheduled transfers into 3 lists: "okay", "canceled" and "impossible".
    """
    canceled_transfers = []
    impossible_transfers = []
    okay_transfers = []
    for tr in transfers:
        tr['amount'] = Money(**tr['amount'])
        beneficiary = tr['beneficiary'] = website.db.Participant.from_id(tr['tippee_id'])
        tip = tr['tip'] = payer.get_tip_to(beneficiary)
        if tip.renewal_mode != 2:
            canceled_transfers.append(tr)
        elif beneficiary.status != 'active' or beneficiary.is_suspended or \
             beneficiary.payment_providers & 1 == 0:
            impossible_transfers.append(tr)
        else:
            okay_transfers.append(tr)
    return okay_transfers, canceled_transfers, impossible_transfers
