from datetime import timedelta
import logging
import re
from time import sleep

import requests
from pando.utils import utcnow

from ..exceptions import PaymentError
from ..i18n.currencies import Money
from ..website import website
from .common import (
    abort_payin, update_payin, update_payin_transfer, record_payin_refund,
    record_payin_transfer_reversal,
)


logger = logging.getLogger('paypal')

session = requests.Session()


def _extract_error_message(response):
    try:
        error = response.json()
        message = error['message']
        assert message
        details = error.get('details')
        if details and isinstance(details, list):
            message = ' | '.join(
                ('%(issue)s: %(description)s' % d if d.get('issue') else d['description'])
                for d in details if d.get('description')
            ) or message
        debug_id = error.get('debug_id')
        if debug_id:
            message += " | PayPal debug_id: " + debug_id
        return message
    except Exception:
        error = response.text  # for Sentry
        logger.debug(error)
        raise PaymentError('PayPal')


def _init_session():
    # TODO switch to bearer tokens to reduce the risk of exposing the long-lived secret
    if 'Authentication' in session.headers:
        return session
    from base64 import b64encode
    session.headers.update({
        'Authorization': 'Basic ' + b64encode((
            '%s:%s' % (website.app_conf.paypal_id, website.app_conf.paypal_secret)
        ).encode('ascii')).decode('ascii'),
    })
    return session


# Version 2
# =========

CAPTURE_STATUSES_MAP = {
    'COMPLETED': 'succeeded',
    'DECLINED': 'failed',
    'PARTIALLY_REFUNDED': 'succeeded',
    'PENDING': 'pending',
    'REFUNDED': 'succeeded',
}
ORDER_STATUSES_MAP = {
    'APPROVED': 'pending',
    'COMPLETED': 'succeeded',
    'CREATED': 'awaiting_payer_action',
    'SAVED': 'pending',
    'VOIDED': 'failed',
}
REFUND_STATUSES_MAP = {
    'CANCELLED': 'failed',
    'COMPLETED': 'succeeded',
    'FAILED': 'failed',
    'PENDING': 'pending',
}

locale_re = re.compile("^[a-z]{2}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}))?$")


def create_order(db, payin, payer, return_url, cancel_url, state):
    """Create an Order.

    Doc: https://developer.paypal.com/docs/api/orders/v2/#orders_create

    Note: even though the API expects a list of purchase_units it rejects the
    request if the list contains more than one of them.
    """
    transfers = db.all("""
        SELECT pt.*
             , recipient.username AS recipient_username
             , team.username AS team_name
             , a.id AS merchant_id
          FROM payin_transfers pt
          JOIN participants recipient ON recipient.id = pt.recipient
     LEFT JOIN participants team ON team.id = pt.team
          JOIN payment_accounts a ON a.pk = pt.destination
         WHERE pt.payin = %s
      ORDER BY pt.id
    """, (payin.id,))
    assert transfers
    locale, _, ngettext = state['locale'], state['_'], state['ngettext']
    # PayPal processes BCP47 tags in a case-sensitive way, and completely rejects
    # requests containing "improperly" cased values.
    locale_tag = (
        locale.language +
        (f'-{locale.script}' if locale.script else '') +
        (f'-{locale.territory}' if locale.territory else '')
    )
    if not locale_re.match(locale_tag):
        website.tell_sentry(Warning(
            f"the locale tag `{locale_tag}` doesn't match the format expected by PayPal; "
            f"falling back to `{locale.language}`"
        ))
        locale_tag = locale.language
    data = {
        "intent": "CAPTURE",
        "application_context": {
            "brand_name": "Liberapay",
            "cancel_url": cancel_url,
            "locale": locale_tag,
            "landing_page": "BILLING",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW",
            "return_url": return_url,
        },
        "purchase_units": [{
            "amount": {
                "value": str(pt.amount.amount),
                "currency_code": pt.amount.currency
            },
            "custom_id": str(pt.id),
            "description": (
                _("Liberapay donation to {username} (team {team_name})",
                  username=pt.recipient_username, team_name=pt.team_name)
                if pt.team_name else
                _("Liberapay donation to {username}", username=pt.recipient_username)
            ) + ' | ' + (ngettext(
                "{n} week of {money_amount}",
                "{n} weeks of {money_amount}",
                n=pt.n_units, money_amount=pt.unit_amount
            ) if pt.period == 'weekly' else ngettext(
                "{n} month of {money_amount}",
                "{n} months of {money_amount}",
                n=pt.n_units, money_amount=pt.unit_amount
            ) if pt.period == 'monthly' else ngettext(
                "{n} year of {money_amount}",
                "{n} years of {money_amount}",
                n=pt.n_units, money_amount=pt.unit_amount
            )),
            "payee": {
                "email_address": pt.merchant_id,
            },
            "reference_id": str(pt.id),
            "soft_descriptor": "Liberapay",
        } for pt in transfers],
    }
    url = 'https://api.%s/v2/checkout/orders' % website.app_conf.paypal_domain
    headers = {
        'PayPal-Request-Id': 'payin_%i' % payin.id
    }
    response = _init_session().post(url, json=data, headers=headers)
    if response.status_code not in (200, 201):
        error = _extract_error_message(response)
        return abort_payin(db, payin, error)
    order = response.json()
    status = ORDER_STATUSES_MAP[order['status']]
    error = order['status'] if status == 'failed' else None
    payin = update_payin(db, payin.id, order['id'], status, error)
    if payin.status == 'awaiting_payer_action':
        redirect_url = [l['href'] for l in order['links'] if l['rel'] == 'approve'][0]
        raise state['response'].redirect(redirect_url)
    return payin


def capture_order(db, payin):
    """Capture a previously approved payment for an order.

    Doc: https://developer.paypal.com/docs/api/orders/v2/#orders_capture
    """
    url = 'https://api.%s/v2/checkout/orders/%s/capture' % (
        website.app_conf.paypal_domain, payin.remote_id
    )
    headers = {
        'PayPal-Request-Id': 'capture_order_%i' % payin.id,
        'Prefer': 'return=representation',
    }
    response = _init_session().post(url, json={}, headers=headers)
    if response.status_code not in (200, 201):
        error = _extract_error_message(response)
        return abort_payin(db, payin, error)
    order = response.json()
    return record_order_result(db, payin, order)


def record_order_result(db, payin, order):
    """Update the status of a payin and its transfers in our database.
    """
    # Update the payin
    status = ORDER_STATUSES_MAP[order['status']]
    if status == 'awaiting_payer_action' and payin.status == 'failed':
        # This payin has already been aborted, don't reset it.
        return payin
    error = order['status'] if status == 'failed' else None
    refunded_amount = sum(
        sum(
            Money(refund['amount']['value'], refund['amount']['currency_code'])
            for refund in pu.get('payments', {}).get('refunds', ())
        )
        for pu in order['purchase_units']
    ) or None
    payin = update_payin(
        db, payin.id, order['id'], status, error, refunded_amount=refunded_amount
    )

    # Update the payin transfers
    for pu in order['purchase_units']:
        pt_id = pu['reference_id']
        reversed_amount = payin.amount.zero()
        for refund in pu.get('payments', {}).get('refunds', ()):
            refund_amount = refund['amount']
            refund_amount = Money(refund_amount['value'], refund_amount['currency_code'])
            reversed_amount += refund_amount
            refund_description = refund.get('note_to_payer')
            refund_status = REFUND_STATUSES_MAP[refund['status']]
            refund_error = refund.get('status_details', {}).get('reason')
            payin_refund = record_payin_refund(
                db, payin.id, refund['id'], refund_amount, None, refund_description,
                refund_status, refund_error, refund['create_time'], notify=False,

            )
            record_payin_transfer_reversal(
                db, pt_id, refund['id'], payin_refund.id, refund['create_time']
            )
        if reversed_amount == 0:
            reversed_amount = None
        for capture in pu.get('payments', {}).get('captures', ()):
            pt_remote_id = capture['id']
            pt_status = CAPTURE_STATUSES_MAP[capture['status']]
            pt_error = capture.get('status_details', {}).get('reason')
            breakdown = capture.get('seller_receivable_breakdown')
            if breakdown and breakdown.get('paypal_fee'):
                pt_fee = breakdown['paypal_fee']
                pt_fee = Money(pt_fee['value'], pt_fee['currency_code'])
                net_amount = breakdown['net_amount']
            else:
                pt_fee = None
                net_amount = capture['amount']
            net_amount = Money(net_amount['value'], net_amount['currency_code'])
            update_payin_transfer(
                db, pt_id, pt_remote_id, pt_status, pt_error,
                amount=net_amount, fee=pt_fee, reversed_amount=reversed_amount
            )

    return payin


def sync_order(db, payin):
    """Fetch the order's data and update our database.

    Doc: https://developer.paypal.com/docs/api/orders/v2/#orders_get
    """
    url = 'https://api.%s/v2/checkout/orders/%s' % (
        website.app_conf.paypal_domain, payin.remote_id
    )
    response = _init_session().get(url)
    if response.status_code != 200:
        if payin.status == 'failed':
            return payin
        try:
            error = response.json()
        except Exception:
            error = {}
        expired = response.status_code == 404 and (
            error.get('message') == "The specified resource does not exist." or
            payin.ctime < (utcnow() - timedelta(days=30))
        )
        if expired:
            return abort_payin(db, payin, "abandoned by payer")
        error = response.text  # for Sentry
        logger.debug(error)
        raise PaymentError('PayPal')
    order = response.json()
    return record_order_result(db, payin, order)


def sync_all_pending_payments(db=None):
    """Calls `sync_order` for every pending payment.
    """
    db = db or website.db
    payins = db.all("""
        SELECT DISTINCT ON (pi.id) pi.*
          FROM payin_transfers pt
          JOIN payins pi ON pi.id = pt.payin
          JOIN exchange_routes r ON r.id = pi.route
         WHERE pt.status = 'pending'
           AND r.network = 'paypal'
      ORDER BY pi.id
    """)
    print("Syncing %i pending PayPal payments..." % len(payins))
    for payin in payins:
        try:
            sync_order(db, payin)
        except Exception as e:
            website.tell_sentry(e)
        sleep(0.2)
