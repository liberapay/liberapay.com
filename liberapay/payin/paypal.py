from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import requests

from ..exceptions import PaymentError
from ..utils.currencies import Money
from ..website import website
from .common import update_payin, update_payin_transfer


PAYMENT_STATES_MAP = {
    'approved': 'succeeded',
    'created': 'pending',
    'failed': 'failed',
}
SALE_STATES_MAP = {
    'completed': 'succeeded',
    'denied': 'failed',
    'pending': 'pending',
}

logger = logging.Logger('paypal')

session = requests.Session()


def _extract_error_message(response):
    try:
        error = response.json()['message']
        assert error
        return error
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


def create_payment(db, payin, payer, return_url, state):
    """Create a Payment.

    Doc: https://developer.paypal.com/docs/api/payments/v1/#payment_create

    Note: even though the API expects a list of transactions it rejects the
    request if the list contains more than one transaction.
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
    locale, _ = state['locale'], state['_']
    data = {
        "intent": "sale",
        "application_context": {
            "brand_name": "Liberapay",
            "locale": locale.language,
            "landing_page": "Login",
            "shipping_preference": "NO_SHIPPING",
            "user_action": "commit",
        },
        "payer": {
            "payment_method": "paypal"
        },
        "transactions": [{
            "amount": {
                "total": str(pt.amount.amount),
                "currency": pt.amount.currency
            },
            "description": (
                _("donation to {0} for their role in the {1} team",
                  pt.recipient_username, pt.team_name)
                if pt.team_name else
                _("donation to {0}", pt.recipient_username)
            ),
            "invoice_number": str(pt.id),
            "note_to_payee": (
                "donation via Liberapay for your role in the %s team" % pt.team_name
                if pt.team_name else
                "donation via Liberapay"
            ),
            "payee": {
                "email": pt.merchant_id,
            },
            "payment_options": {
                "allowed_payment_method": "UNRESTRICTED"
            },
            "soft_descriptor": "Liberapay",
        } for pt in transfers],
        "redirect_urls": {
            "return_url": return_url,
            "cancel_url": return_url
        }
    }
    url = 'https://api.%s/v1/payments/payment' % website.app_conf.paypal_domain
    headers = {
        'PayPal-Request-Id': 'payin_%i' % payin.id
    }
    response = _init_session().post(url, json=data, headers=headers)
    if response.status_code != 201:
        error = _extract_error_message(response)
        return update_payin(db, payin.id, None, 'failed', error)
    payment = response.json()
    status = PAYMENT_STATES_MAP[payment['state']]
    error = payment.get('failure_reason')
    payin = update_payin(db, payin.id, payment['id'], status, error)
    if payin.status == 'pending':
        redirect_url = [l['href'] for l in payment['links'] if l['rel'] == 'approval_url'][0]
        raise state['response'].redirect(redirect_url)
    return payin


def execute_payment(db, payin, payer_id):
    """Execute a previously approved payment.

    Doc: https://developer.paypal.com/docs/api/payments/v1/#payment_execute
    """
    url = 'https://api.%s/v1/payments/payment/%s/execute' % (
        website.app_conf.paypal_domain, payin.remote_id
    )
    headers = {'PayPal-Request-Id': 'payin_execute_%i' % payin.id}
    data = {"payer_id": payer_id}
    response = _init_session().post(url, json=data, headers=headers)
    if response.status_code != 200:
        error = _extract_error_message(response)
        return update_payin(db, payin.id, None, 'failed', error)
    payment = response.json()

    # Update the payin
    status = PAYMENT_STATES_MAP[payment['state']]
    error = payment.get('failure_reason')
    payin = update_payin(db, payin.id, payment['id'], status, error)

    # Update the payin transfers
    for tr in payment['transactions']:
        sale = tr.get('related_resources', [{}])[0].get('sale')
        if sale:
            pt_id = tr['invoice_number']
            pt_remote_id = sale['id']
            pt_status = SALE_STATES_MAP[sale['state']]
            pt_error = sale.get('reason_code')
            pt_fee = sale.get('transaction_fee')
            if pt_fee:
                pt_fee = Money(pt_fee['value'], pt_fee['currency'])
            charge_amount = Money(sale['amount']['total'], sale['amount']['currency'])
            net_amount = charge_amount - (pt_fee or 0)
            update_payin_transfer(
                db, pt_id, pt_remote_id, pt_status, pt_error,
                amount=net_amount, fee=pt_fee
            )

    return payin


def sync_payment(db, payin):
    """Fetch the payment's data and update our database.

    Doc: https://developer.paypal.com/docs/api/payments/v1/#payment_get
    """
    url = 'https://api.%s/v1/payments/payment/%s' % (
        website.app_conf.paypal_domain, payin.remote_id
    )
    response = _init_session().get(url)
    if response.status_code != 200:
        error = response.text  # for Sentry
        logger.debug(error)
        raise PaymentError('PayPal')
    payment = response.json()
    status = PAYMENT_STATES_MAP[payment['state']]
    error = payment.get('failure_reason')
    return update_payin(db, payin.id, payment['id'], status, error)
