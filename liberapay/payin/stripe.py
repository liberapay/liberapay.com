from datetime import timedelta
from decimal import Decimal

import stripe
import stripe.error

from ..constants import EPOCH, PAYIN_SETTLEMENT_DELAYS
from ..exceptions import NextAction
from ..i18n.currencies import Money
from ..models.exchange_route import ExchangeRoute
from ..website import website
from .common import (
    abort_payin, adjust_payin_transfers,
    record_payin_refund, record_payin_transfer_reversal,
    update_payin, update_payin_transfer,
)


REFUND_REASONS_MAP = {
    None: None,
    'duplicate': 'duplicate',
    'fraudulent': 'fraud',
    'requested_by_customer': 'requested_by_payer',
}

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


def create_source_from_token(token_id, one_off, amount, owner_info, return_url):
    token = stripe.Token.retrieve(token_id)
    if token.type == 'bank_account':
        source_type = 'sepa_debit'
    elif token.type == 'card':
        source_type = 'card'
    else:
        raise NotImplementedError(token.type)
    return stripe.Source.create(
        amount=Money_to_int(amount) if one_off and amount else None,
        owner=owner_info,
        redirect={'return_url': return_url},
        token=token.id,
        type=source_type,
        usage=('single_use' if one_off and amount and source_type == 'card' else 'reusable'),
        idempotency_key='create_source_from_%s' % token.id,
    )


def charge(db, payin, payer):
    """Initiate the Charge for the given payin.

    Returns the update payin.

    """
    n_transfers = db.one("""
        SELECT count(*)
          FROM payin_transfers pt
         WHERE pt.payin = %(payin)s
    """, dict(payin=payin.id))
    if n_transfers == 1:
        return destination_charge(
            db, payin, payer, statement_descriptor=('Liberapay %i' % payin.id)
        )
    else:
        return charge_and_transfer(
            db, payin, payer, statement_descriptor=('Liberapay %i' % payin.id)
        )


def charge_and_transfer(db, payin, payer, statement_descriptor, on_behalf_of=None):
    """Create a standalone Charge then multiple Transfers.

    Doc: https://stripe.com/docs/connect/charges-transfers

    As of January 2019 this only works if the recipients are in the SEPA.

    """
    assert payer.id == payin.payer
    amount = payin.amount
    route = ExchangeRoute.from_id(payer, payin.route)
    intent = None
    try:
        if route.address.startswith('pm_'):
            intent = stripe.PaymentIntent.create(
                amount=Money_to_int(amount),
                confirm=True,
                currency=amount.currency.lower(),
                customer=route.remote_user_id,
                metadata={'payin_id': payin.id},
                on_behalf_of=on_behalf_of,
                payment_method=route.address,
                return_url=payer.url('giving/pay/stripe/%i' % payin.id),
                statement_descriptor=statement_descriptor,
                idempotency_key='payin_intent_%i' % payin.id,
            )
        else:
            charge = stripe.Charge.create(
                amount=Money_to_int(amount),
                currency=amount.currency.lower(),
                customer=route.remote_user_id,
                metadata={'payin_id': payin.id},
                on_behalf_of=on_behalf_of,
                source=route.address,
                statement_descriptor=statement_descriptor,
                expand=['balance_transaction'],
                idempotency_key='payin_%i' % payin.id,
            )
    except stripe.error.StripeError as e:
        return abort_payin(db, payin, repr_stripe_error(e))
    except Exception as e:
        website.tell_sentry(e, {})
        return abort_payin(db, payin, str(e))
    if intent:
        if intent.status == 'requires_action':
            update_payin(db, payin.id, None, 'awaiting_payer_action', None,
                         intent_id=intent.id)
            raise NextAction(intent)
        else:
            charge = intent.charges.data[0]
    intent_id = getattr(intent, 'id', None)
    payin = settle_charge_and_transfers(db, payin, charge, intent_id=intent_id)
    send_payin_notification(payin, payer, charge, route)
    return payin


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
    intent = None
    if destination == 'acct_1ChyayFk4eGpfLOC':
        # Stripe rejects the charge if the destination is our own account
        destination = None
    try:
        if route.address.startswith('pm_'):
            intent = stripe.PaymentIntent.create(
                amount=Money_to_int(amount),
                confirm=True,
                currency=amount.currency.lower(),
                customer=route.remote_user_id,
                metadata={'payin_id': payin.id},
                on_behalf_of=destination,
                payment_method=route.address,
                return_url=payer.url('giving/pay/stripe/%i' % payin.id),
                statement_descriptor=statement_descriptor,
                transfer_data={'destination': destination} if destination else None,
                idempotency_key='payin_intent_%i' % payin.id,
            )
        else:
            charge = stripe.Charge.create(
                amount=Money_to_int(amount),
                currency=amount.currency.lower(),
                customer=route.remote_user_id,
                destination={'account': destination} if destination else None,
                metadata={'payin_id': payin.id},
                source=route.address,
                statement_descriptor=statement_descriptor,
                expand=['balance_transaction'],
                idempotency_key='payin_%i' % payin.id,
            )
    except stripe.error.StripeError as e:
        return abort_payin(db, payin, repr_stripe_error(e))
    except Exception as e:
        website.tell_sentry(e, {})
        return abort_payin(db, payin, str(e))
    if intent:
        if intent.status == 'requires_action':
            update_payin(db, payin.id, None, 'awaiting_payer_action', None,
                         intent_id=intent.id)
            raise NextAction(intent)
        else:
            charge = intent.charges.data[0]
    intent_id = getattr(intent, 'id', None)
    payin = settle_destination_charge(db, payin, charge, pt, intent_id=intent_id)
    send_payin_notification(payin, payer, charge, route)
    return payin


def send_payin_notification(payin, payer, charge, route):
    """Send the legally required notification for SEPA Direct Debits.
    """
    if route.network == 'stripe-sdd' and charge.status != 'failed':
        if route.address.startswith('pm_'):
            raise NotImplementedError()
        else:
            sepa_debit = stripe.Source.retrieve(route.address).sepa_debit
        payer.notify(
            'payin_sdd_created',
            force_email=True,
            email_unverified_address=True,
            payin_id=payin.id,  # unused but required for uniqueness
            payin_amount=payin.amount,
            bank_name=getattr(sepa_debit, 'bank_name', None),
            partial_bank_account_number=get_partial_iban(sepa_debit),
            mandate_url=sepa_debit.mandate_url,
            mandate_id=sepa_debit.mandate_reference,
            mandate_creation_date=route.ctime.date(),
            creditor_identifier=website.app_conf.sepa_creditor_identifier,
            average_settlement_seconds=PAYIN_SETTLEMENT_DELAYS['stripe-sdd'].total_seconds(),
        )


def settle_payin(db, payin):
    """Check the status of a payin, take appropriate action if it has changed.
    """
    if payin.intent_id:
        intent = stripe.PaymentIntent.retrieve(payin.intent_id)
        if intent.status == 'requires_action':
            raise NextAction(intent)
        err = intent.last_payment_error
        if err and intent.status in ('requires_payment_method', 'canceled'):
            charge_id = getattr(err, 'charge', None)
            return update_payin(db, payin.id, charge_id, 'failed', err.message)
        if intent.charges.data:
            charge = intent.charges.data[0]
        else:
            return payin
    else:
        charge = stripe.Charge.retrieve(payin.remote_id)
    return settle_charge(db, payin, charge)


def settle_charge(db, payin, charge):
    """Handle a charge's status change.
    """
    if charge.destination:
        pt = db.one("SELECT * FROM payin_transfers WHERE payin = %s", (payin.id,))
        return settle_destination_charge(db, payin, charge, pt)
    else:
        return settle_charge_and_transfers(db, payin, charge)


def settle_charge_and_transfers(db, payin, charge, intent_id=None):
    """Record the result of a charge, and execute the transfers if it succeeded.
    """
    if getattr(charge, 'balance_transaction', None):
        bt = charge.balance_transaction
        if isinstance(bt, str):
            bt = stripe.BalanceTransaction.retrieve(bt)
        amount_settled = int_to_Money(bt.amount, bt.currency)
        fee = int_to_Money(bt.fee, bt.currency)
        net_amount = amount_settled - fee
    else:
        amount_settled, fee, net_amount = None, None, None

    error = repr_charge_error(charge)
    refunded_amount, refund_ratio = None, None
    if charge.amount_refunded:
        refunded_amount = int_to_Money(charge.amount_refunded, charge.currency)
        refund_ratio = refunded_amount / payin.amount
    payin = update_payin(
        db, payin.id, charge.id, charge.status, error,
        amount_settled=amount_settled, fee=fee, intent_id=intent_id,
        refunded_amount=refunded_amount,
    )

    if charge.refunds.data:
        record_refunds(db, payin, charge)

    if amount_settled is not None:
        adjust_payin_transfers(db, payin, net_amount)

    payin_transfers = db.all("""
        SELECT pt.*, pa.id AS destination_id
          FROM payin_transfers pt
          JOIN payment_accounts pa ON pa.pk = pt.destination
         WHERE pt.payin = %s
      ORDER BY pt.id
    """, (payin.id,))
    if amount_settled is not None:
        for pt in payin_transfers:
            if pt.destination_id == 'acct_1ChyayFk4eGpfLOC':
                if refund_ratio:
                    pt_reversed_amount = (pt.amount * refund_ratio).round_up()
                else:
                    pt_reversed_amount = None
                update_payin_transfer(
                    db, pt.id, None, charge.status, error,
                    reversed_amount=pt_reversed_amount,
                )
            elif pt.remote_id is None and pt.status in ('pre', 'pending'):
                execute_transfer(db, pt, pt.destination_id, charge.id)
            elif refunded_amount and pt.remote_id:
                sync_transfer(db, pt)
    elif charge.status in ('failed', 'pending'):
        for pt in payin_transfers:
            update_payin_transfer(db, pt.id, None, charge.status, error)

    return payin


def execute_transfer(db, pt, destination, source_transaction):
    """Create a Transfer.

    Args:
        pt (Record): a row from the `payin_transfers` table
        destination (str): the Stripe ID of the destination account
        source_transaction (str): the ID of the Charge this transfer is linked to

    Returns:
        Record: the row updated in the `payin_transfers` table

    """
    assert pt.remote_id is None
    try:
        tr = stripe.Transfer.create(
            amount=Money_to_int(pt.amount),
            currency=pt.amount.currency,
            destination=destination,
            metadata={'payin_transfer_id': pt.id},
            source_transaction=source_transaction,
            idempotency_key='payin_transfer_%i' % pt.id,
        )
    except stripe.error.StripeError as e:
        website.tell_sentry(e, {})
        return update_payin_transfer(db, pt.id, '', 'failed', repr_stripe_error(e))
    except Exception as e:
        website.tell_sentry(e, {})
        return update_payin_transfer(db, pt.id, '', 'failed', str(e))
    # `Transfer` objects don't have a `status` attribute, so if no exception was
    # raised we assume that the transfer was successful.
    return update_payin_transfer(db, pt.id, tr.id, 'succeeded', None)


def sync_transfer(db, pt):
    """Fetch the transfer's data and update our database.

    Args:
        pt (Record): a row from the `payin_transfers` table

    Returns:
        Record: the row updated in the `payin_transfers` table

    """
    assert pt.remote_id, "can't sync a transfer lacking a `remote_id`"
    tr = stripe.Transfer.retrieve(pt.remote_id)
    if tr.amount_reversed:
        reversed_amount = min(int_to_Money(tr.amount_reversed, tr.currency), pt.amount)
    else:
        reversed_amount = None
    record_reversals(db, pt, tr)
    return update_payin_transfer(
        db, pt.id, tr.id, 'succeeded', None, reversed_amount=reversed_amount
    )


def settle_destination_charge(db, payin, charge, pt, intent_id=None):
    """Record the result of a charge, and recover the fee.
    """
    if getattr(charge, 'balance_transaction', None):
        bt = charge.balance_transaction
        if isinstance(bt, str):
            bt = stripe.BalanceTransaction.retrieve(bt)
        amount_settled = int_to_Money(bt.amount, bt.currency)
        fee = int_to_Money(bt.fee, bt.currency)
        net_amount = amount_settled - fee
    else:
        amount_settled, fee, net_amount = None, None, payin.amount

    status = charge.status
    error = repr_charge_error(charge)
    refunded_amount = None
    if charge.amount_refunded:
        refunded_amount = int_to_Money(charge.amount_refunded, charge.currency)

    payin = update_payin(
        db, payin.id, charge.id, status, error,
        amount_settled=amount_settled, fee=fee, intent_id=intent_id,
        refunded_amount=refunded_amount,
    )

    if charge.refunds.data:
        record_refunds(db, payin, charge)

    reversed_amount = None
    if getattr(charge, 'transfer', None):
        tr = stripe.Transfer.retrieve(charge.transfer)
        if tr.amount_reversed == 0:
            tr.reversals.create(
                amount=bt.fee,
                description="Stripe fee",
                metadata={'payin_id': payin.id},
                idempotency_key='payin_fee_%i' % payin.id,
            )
        elif tr.amount_reversed > bt.fee:
            reversed_amount = int_to_Money(tr.amount_reversed, tr.currency) - fee
            record_reversals(db, pt, tr)

    pt_remote_id = getattr(charge, 'transfer', None)
    pt = update_payin_transfer(
        db, pt.id, pt_remote_id, status, error, amount=net_amount,
        reversed_amount=reversed_amount,
    )

    return payin


def record_refunds(db, payin, charge):
    """Record charge refunds in our database.

    Args:
        payin (Record): a row from the `payins` table
        charge (Charge): a `stripe.Charge` object

    Returns: the list of rows upserted into the `payin_refunds` table

    """
    r = []
    for refund in charge.refunds.auto_paging_iter():
        rf_amount = int_to_Money(refund.amount, refund.currency)
        rf_reason = REFUND_REASONS_MAP[refund.reason]
        rf_description = getattr(refund, 'description', None)
        r.append(record_payin_refund(
            db, payin.id, refund.id, rf_amount, rf_reason, rf_description,
            refund.status, error=getattr(refund, 'failure_reason', None),
            ctime=(EPOCH + timedelta(seconds=refund.created)),
        ))
    return r


def record_reversals(db, pt, transfer):
    """Record transfer reversals in our database.

    Args:
        pt (Record): a row from the `payin_transfers` table
        transfer (Transfer): a `stripe.Transfer` object

    Returns: the list of rows upserted into the `payin_transfer_reversals` table

    """
    r = []
    fee = transfer.amount - Money_to_int(pt.amount)
    for reversal in transfer.reversals.auto_paging_iter():
        if reversal.amount == fee and reversal.id == transfer.reversals.data[-1].id:
            continue
        reversal_amount = int_to_Money(reversal.amount, reversal.currency)
        payin_refund_id = db.one("""
            SELECT pr.id
              FROM payin_refunds pr
             WHERE pr.payin = %s
               AND pr.remote_id = %s
        """, (pt.payin, reversal.source_refund))
        r.append(record_payin_transfer_reversal(
            db, pt.id, reversal.id, reversal_amount, payin_refund_id=payin_refund_id,
            ctime=(EPOCH + timedelta(seconds=reversal.created)),
        ))
    return r
