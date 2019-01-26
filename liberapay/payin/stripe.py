# coding: utf8

from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal

import stripe
import stripe.error

from ..i18n.currencies import Money
from ..models.exchange_route import ExchangeRoute
from ..website import website
from .common import update_payin, update_payin_transfer


# https://stripe.com/docs/currencies#presentment-currencies
ZERO_DECIMAL_CURRENCIES = """
    BIF CLP DJF GNF JPY KMF KRW MGA PYG RWF UGX VND VUV XAF XOF XPF
""".split()


def int_to_Money(amount, currency):
    currency = currency.upper()
    if currency in ZERO_DECIMAL_CURRENCIES:
        return Money(Decimal(amount), currency)
    return Money(Decimal(amount) / 100, currency)


def Money_to_int(m):
    if m.currency in ZERO_DECIMAL_CURRENCIES:
        return int(m.amount)
    return int(m.amount * 100)


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


def get_partial_iban(sepa_debit):
    return '%s⋯%s' % (sepa_debit.country, sepa_debit.last4)


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
            amount=Money_to_int(amount),
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
        website.tell_sentry(e, {})
        return update_payin(db, payin.id, '', 'failed', str(e))
    payin = settle_destination_charge(db, payin, charge, pt)
    if route.network == 'stripe-sdd' and payin.status != 'failed':
        sepa_debit = stripe.Source.retrieve(route.address).sepa_debit
        payer.notify(
            'payin_sdd_created',
            force_email=True,
            payin_amount=payin.amount,
            bank_name=getattr(sepa_debit, 'bank_name', None),
            partial_bank_account_number=get_partial_iban(sepa_debit),
            mandate_url=sepa_debit.mandate_url,
            mandate_id=sepa_debit.mandate_reference,
            mandate_creation_date=route.ctime.date(),
            creditor_identifier=website.app_conf.sepa_creditor_identifier,
            statement_descriptor=charge.statement_descriptor,
        )
    return payin


def settle_destination_charge(db, payin, charge, pt):
    """Record the result of a charge, and recover the fee.
    """
    if getattr(charge, 'balance_transaction', None):
        bt = charge.balance_transaction
        if isinstance(bt, str):
            bt = stripe.BalanceTransaction.retrieve(bt)
        amount_settled = int_to_Money(bt.amount, bt.currency)
        fee = int_to_Money(bt.fee, bt.currency)
        net_amount = amount_settled - fee

        if getattr(charge, 'transfer', None):
            tr = stripe.Transfer.retrieve(charge.transfer)
            if tr.amount_reversed == 0:
                tr.reversals.create(
                    amount=bt.fee,
                    description="Stripe fee",
                    metadata={'payin_id': payin.id},
                    idempotency_key='payin_fee_%i' % payin.id,
                )
    else:
        amount_settled, fee, net_amount = None, None, payin.amount

    status = charge.status
    error = repr_charge_error(charge)

    payin = update_payin(
        db, payin.id, charge.id, status, error,
        amount_settled=amount_settled, fee=fee
    )

    pt_remote_id = getattr(charge, 'transfer', None)
    pt = update_payin_transfer(
        db, pt.id, pt_remote_id, status, error, amount=net_amount
    )

    return payin
