from decimal import Decimal
from time import sleep

from psycopg2.extras import execute_batch
import stripe
import stripe.error

from ..exceptions import NextAction
from ..i18n.currencies import Money
from ..models.exchange_route import ExchangeRoute
from ..website import website
from .common import abort_payin, resolve_amounts, update_payin, update_payin_transfer


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
            payin_id=payin.id,  # unused but required for uniqueness
            payin_amount=payin.amount,
            bank_name=getattr(sepa_debit, 'bank_name', None),
            partial_bank_account_number=get_partial_iban(sepa_debit),
            mandate_url=sepa_debit.mandate_url,
            mandate_id=sepa_debit.mandate_reference,
            mandate_creation_date=route.ctime.date(),
            creditor_identifier=website.app_conf.sepa_creditor_identifier,
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
    payin = update_payin(
        db, payin.id, charge.id, charge.status, error,
        amount_settled=amount_settled, fee=fee, intent_id=intent_id
    )

    if amount_settled is not None:
        # We have to update the transfer amounts in a single transaction to
        # avoid ending up in an inconsistent state.
        with db.get_cursor() as cursor:
            payin_transfers = cursor.all("""
                SELECT id, amount
                  FROM payin_transfers
                 WHERE payin = %s
              ORDER BY id
                   FOR UPDATE
            """, (payin.id,))
            transfer_amounts = resolve_amounts(net_amount, {
                pt.id: pt.amount.convert(amount_settled.currency) for pt in payin_transfers
            })
            args_list = [
                (transfer_amounts[pt.id], pt.id) for pt in payin_transfers
                if pt.amount != transfer_amounts[pt.id]
            ]
            if args_list:
                execute_batch(cursor, """
                    UPDATE payin_transfers
                       SET amount = %s
                     WHERE id = %s
                       AND status <> 'succeeded';
                """, args_list)

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
                update_payin_transfer(db, pt.id, None, charge.status, error)
            elif pt.status == 'pre':
                execute_transfer(db, pt, pt.destination_id, charge.id)
    elif charge.status == 'failed':
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
        if e.code == 'idempotency_key_in_use':
            # Two threads are submitting this same request at the same time,
            # retry in a second.
            sleep(1)
            return execute_transfer(db, pt, destination, source_transaction)
        website.tell_sentry(e, {})
        return update_payin_transfer(db, pt.id, '', 'failed', repr_stripe_error(e))
    except Exception as e:
        website.tell_sentry(e, {})
        return update_payin_transfer(db, pt.id, '', 'failed', str(e))
    # `Transfer` objects don't have a `status` attribute, so if no exception was
    # raised we assume that the transfer was successful.
    return update_payin_transfer(db, pt.id, tr.id, 'succeeded', None)


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
        amount_settled=amount_settled, fee=fee, intent_id=intent_id
    )

    pt_remote_id = getattr(charge, 'transfer', None)
    pt = update_payin_transfer(
        db, pt.id, pt_remote_id, status, error, amount=net_amount
    )

    return payin
