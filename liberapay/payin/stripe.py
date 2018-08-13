from __future__ import absolute_import, division, print_function, unicode_literals

import stripe
import stripe.error

from ..models.exchange_route import ExchangeRoute
from ..utils.currencies import Money
from .common import update_payin


def repr_stripe_error(e):
    """Given a `StripeError` exception, return an error message suitable for display.
    """
    msg = e.user_message or e.code
    return '%s (request ID: %s)' % (msg, e.request_id)


def repr_charge_error(charge):
    """Given a `Charge` object, return an error message suitable for display.
    """
    if charge.status != 'failed':
        return
    return '%s (code %s)' % (charge.failure_message, charge.failure_code)


def destination_charge(db, payin, payer, statement_descriptor):
    """Create a Destination Charge.

    Doc: https://stripe.com/docs/connect/destination-charges

    Destination charges don't have built-in support for processing payments
    "at cost", so we (mis)use transfer reversals to recover the exact amount of
    the Stripe fee.

    """
    assert payer.id == payin.payer
    pt = db.one("SELECT * FROM payin_transfers WHERE payin = %s", (payin.id,))
    destination = db.one("SELECT id FROM payment_accounts WHERE pk = %s", (pt.destination,))
    amount = payin.amount
    route = ExchangeRoute.from_id(payer, payin.route)
    if destination == 'acct_1ChyayFk4eGpfLOC':
        # Stripe rejects the charge if the destination is our own account
        destination = None
    else:
        destination = {'account': destination}
    try:
        charge = stripe.Charge.create(
            amount=amount.int().amount,
            currency=amount.currency.lower(),
            customer=route.remote_user_id,
            destination=destination,
            metadata={'payin_id': payin.id},
            source=route.address,
            statement_descriptor=statement_descriptor,
            expand=['balance_transaction'],
            idempotency_key='payin_%i' % payin.id,
        )
    except stripe.error.StripeError as e:
        return update_payin(db, payin.id, '', 'failed', repr_stripe_error(e))
    except Exception as e:
        from liberapay.website import website
        website.tell_sentry(e, {})
        return update_payin(db, payin.id, '', 'failed', str(e))

    bt = charge.balance_transaction
    amount_settled = Money(bt.amount, bt.currency.upper()) / 100
    fee = Money(bt.fee, bt.currency.upper()) / 100
    net_amount = amount_settled - fee

    if destination:
        tr = stripe.Transfer.retrieve(charge.transfer)
        reversal = tr.reversals.create(
            amount=bt.fee,
            description="Stripe fee",
            metadata={'payin_id': payin.id},
            idempotency_key='payin_fee_%i' % payin.id,
        )

    r = db.one("""
        UPDATE payin_transfers
           SET status = %s
             , remote_id = %s
             , amount = %s
         WHERE payin = %s
     RETURNING id
    """, (payin.status, getattr(charge, 'transfer', None), net_amount, payin.id))
    assert r, locals()

    return update_payin(
        db, payin.id, charge.id, charge.status, repr_charge_error(charge),
        amount_settled=amount_settled, fee=fee
    )
