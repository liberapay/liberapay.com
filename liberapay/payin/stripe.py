from datetime import timedelta
from decimal import Decimal

import stripe
import stripe.error

from ..constants import EPOCH, PAYIN_SETTLEMENT_DELAYS
from ..exceptions import MissingPaymentAccount, NextAction, NoSelfTipping
from ..i18n.currencies import Money
from ..models.exchange_route import ExchangeRoute
from ..website import website
from .common import (
    abort_payin, adjust_payin_transfers, prepare_payin,
    record_payin_refund, record_payin_transfer_reversal, resolve_tip,
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


def charge(db, payin, payer, route):
    """Initiate the Charge for the given payin.

    Returns the updated payin, or possibly a new payin.

    """
    assert payin.route == route.id
    n_transfers = db.one("""
        SELECT count(*)
          FROM payin_transfers pt
         WHERE pt.payin = %(payin)s
    """, dict(payin=payin.id))
    if n_transfers == 1:
        payin, charge = destination_charge(
            db, payin, payer, statement_descriptor=('Liberapay %i' % payin.id)
        )
        if payin.status == 'failed':
            payin, charge = try_other_destinations(db, payin, payer, charge)
    else:
        payin, charge = charge_and_transfer(
            db, payin, payer, statement_descriptor=('Liberapay %i' % payin.id)
        )
    if charge and charge.status == 'failed' and charge.failure_code == 'expired_card':
        route.update_status('expired')
    return payin


def try_other_destinations(db, payin, payer, charge):
    """Retry a failed charge with different destinations.

    Returns a payin.

    """
    first_payin_id = payin.id
    tippee_id = db.one("""
        SELECT coalesce(team, recipient) AS tippee
          FROM payin_transfers
         WHERE payin = %s
    """, (payin.id,))
    tippee = db.Participant.from_id(tippee_id)
    tip = db.one("""
        SELECT t.*, p AS tippee_p
          FROM current_tips t
          JOIN participants p ON p.id = t.tippee
         WHERE t.tipper = %s
           AND t.tippee = %s
    """, (payer.id, tippee_id))
    route = ExchangeRoute.from_id(payer, payin.route, _raise=False)
    if not (tip and route):
        return payin, charge
    excluded_destinations = set()
    while payin.status == 'failed':
        error = payin.error
        reroute = (
            error.startswith("As per Indian regulations, ") or
            error.startswith("For 'sepa_debit' payments, we currently require ") or
            error.startswith("Stripe doesn't currently support ")
        )
        if reroute:
            excluded_destinations.add(db.one("""
                SELECT destination
                  FROM payin_transfers
                 WHERE payin = %s
            """, (payin.id,)))
        else:
            break
        try:
            proto_transfers = resolve_tip(
                db, tip, tippee, 'stripe', payer, route.country, payin.amount,
                excluded_destinations=excluded_destinations,
            )
        except (MissingPaymentAccount, NoSelfTipping):
            break
        try:
            payin, payin_transfers = prepare_payin(
                db, payer, payin.amount, route, proto_transfers,
                off_session=payin.off_session,
            )
            if len(payin_transfers) == 1:
                payin, charge = destination_charge(
                    db, payin, payer, statement_descriptor=('Liberapay %i' % payin.id)
                )
            else:
                payin, charge = charge_and_transfer(
                    db, payin, payer, statement_descriptor=('Liberapay %i' % payin.id)
                )
        except NextAction:
            raise
        except Exception as e:
            website.tell_sentry(e)
            break
    if payin.id != first_payin_id:
        db.run("""
            UPDATE scheduled_payins
               SET payin = %s
                 , mtime = current_timestamp
             WHERE payin = %s
        """, (payin.id, first_payin_id))
    return payin, charge


def charge_and_transfer(db, payin, payer, statement_descriptor, on_behalf_of=None):
    """Create a standalone Charge then multiple Transfers.

    Doc: https://stripe.com/docs/connect/charges-transfers

    As of January 2019 this only works if the recipients are in the SEPA.

    """
    assert payer.id == payin.payer
    amount = payin.amount
    route = ExchangeRoute.from_id(payer, payin.route)
    intent = None
    description = generate_charge_description(payin)
    try:
        if route.address.startswith('pm_'):
            intent = stripe.PaymentIntent.create(
                amount=Money_to_int(amount),
                confirm=True,
                currency=amount.currency.lower(),
                customer=route.remote_user_id,
                description=description,
                metadata={'payin_id': payin.id},
                off_session=payin.off_session,
                on_behalf_of=on_behalf_of,
                payment_method=route.address,
                return_url=payer.url('giving/pay/stripe/%i' % payin.id),
                setup_future_usage=(None if route.one_off or payin.off_session else 'off_session'),
                statement_descriptor=statement_descriptor,
                idempotency_key='payin_intent_%i' % payin.id,
            )
        else:
            charge = stripe.Charge.create(
                amount=Money_to_int(amount),
                currency=amount.currency.lower(),
                customer=route.remote_user_id,
                description=description,
                metadata={'payin_id': payin.id},
                on_behalf_of=on_behalf_of,
                source=route.address,
                statement_descriptor=statement_descriptor,
                expand=['balance_transaction'],
                idempotency_key='payin_%i' % payin.id,
            )
    except stripe.error.StripeError as e:
        return abort_payin(db, payin, repr_stripe_error(e)), None
    except Exception as e:
        website.tell_sentry(e)
        return abort_payin(db, payin, str(e)), None
    if intent:
        if intent.status == 'requires_action':
            update_payin(db, payin.id, None, 'awaiting_payer_action', None,
                         intent_id=intent.id)
            raise NextAction(intent)
        else:
            charge = intent.charges.data[0]
    intent_id = getattr(intent, 'id', None)
    payin = settle_charge_and_transfers(db, payin, charge, intent_id=intent_id)
    send_payin_notification(db, payin, payer, charge, route)
    return payin, charge


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
    description = generate_charge_description(payin)
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
                description=description,
                metadata={'payin_id': payin.id},
                off_session=payin.off_session,
                on_behalf_of=destination,
                payment_method=route.address,
                return_url=payer.url('giving/pay/stripe/%i' % payin.id),
                setup_future_usage=(None if route.one_off or payin.off_session else 'off_session'),
                statement_descriptor=statement_descriptor,
                transfer_data={'destination': destination} if destination else None,
                idempotency_key='payin_intent_%i' % payin.id,
            )
        else:
            charge = stripe.Charge.create(
                amount=Money_to_int(amount),
                currency=amount.currency.lower(),
                customer=route.remote_user_id,
                description=description,
                destination={'account': destination} if destination else None,
                metadata={'payin_id': payin.id},
                source=route.address,
                statement_descriptor=statement_descriptor,
                expand=['balance_transaction'],
                idempotency_key='payin_%i' % payin.id,
            )
    except stripe.error.StripeError as e:
        return abort_payin(db, payin, repr_stripe_error(e)), None
    except Exception as e:
        website.tell_sentry(e)
        return abort_payin(db, payin, str(e)), None
    if intent:
        if intent.status == 'requires_action':
            update_payin(db, payin.id, None, 'awaiting_payer_action', None,
                         intent_id=intent.id)
            raise NextAction(intent)
        else:
            charge = intent.charges.data[0]
    intent_id = getattr(intent, 'id', None)
    payin = settle_destination_charge(db, payin, charge, pt, intent_id=intent_id)
    send_payin_notification(db, payin, payer, charge, route)
    return payin, charge


def send_payin_notification(db, payin, payer, charge, route):
    """Send the legally required notification for SEPA Direct Debits.
    """
    if route.network == 'stripe-sdd' and charge.status != 'failed':
        if route.address.startswith('pm_'):
            raise NotImplementedError()
        else:
            sepa_debit = stripe.Source.retrieve(route.address).sepa_debit
        tippees = db.all("""
            SELECT DISTINCT tippee_p.id AS tippee_id, tippee_p.username AS tippee_username
              FROM payin_transfers pt
              JOIN participants tippee_p ON tippee_p.id = coalesce(pt.team, pt.recipient)
             WHERE pt.payin = %s
        """, (payin.id,), back_as=dict)
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
            tippees=tippees,
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
    refunded_amount = None
    if charge.amount_refunded:
        refunded_amount = int_to_Money(charge.amount_refunded, charge.currency)
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
        payer = db.Participant.from_id(payin.payer)
        if payer.is_suspended:
            return payin
        undeliverable_amount = amount_settled.zero()
        for i, pt in enumerate(payin_transfers):
            destination_id = pt.destination_id
            if destination_id == 'acct_1ChyayFk4eGpfLOC':
                pt = update_payin_transfer(db, pt.id, None, charge.status, error)
            elif pt.remote_id is None and pt.status in ('pre', 'pending'):
                pt = execute_transfer(db, pt, destination_id, charge.id)
                if pt.status == 'failed' and pt.error.startswith("No such destination: "):
                    undeliverable_amount += pt.amount
                    db.run("""
                        UPDATE payment_accounts
                           SET is_current = null
                         WHERE provider = 'stripe'
                           AND id = %s
                    """, (destination_id,))
            elif refunded_amount and pt.remote_id:
                pt = sync_transfer(db, pt)
            payin_transfers[i] = pt
        del destination_id
        if undeliverable_amount:
            refund_ratio = undeliverable_amount / net_amount
            refund_amount = (payin.amount * refund_ratio).round_up()
            try:
                payin = refund_payin(db, payin, refund_amount=refund_amount)
            except Exception as e:
                website.tell_sentry(e)
        if refunded_amount == payin.amount and payin.ctime.year >= 2021:
            payin_refund_id = db.one("""
                SELECT pr.id
                  FROM payin_refunds pr
                 WHERE pr.payin = %s
                   AND pr.amount = %s
                   AND pr.status <> 'failed'
              ORDER BY pr.ctime
                 LIMIT 1
            """, (payin.id, payin.amount))
            for i, pt in enumerate(payin_transfers):
                if pt.status == 'succeeded':
                    payin_transfers[i] = reverse_transfer(
                        db, pt, payin_refund_id=payin_refund_id
                    )

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
            description=generate_transfer_description(pt),
            destination=destination,
            metadata={'payin_transfer_id': pt.id},
            source_transaction=source_transaction,
            idempotency_key='payin_transfer_%i' % pt.id,
        )
    except stripe.error.StripeError as e:
        website.tell_sentry(e, allow_reraise=False)
        return update_payin_transfer(db, pt.id, '', 'failed', repr_stripe_error(e))
    except Exception as e:
        website.tell_sentry(e)
        return update_payin_transfer(db, pt.id, '', 'failed', str(e))
    # `Transfer` objects don't have a `status` attribute, so if no exception was
    # raised we assume that the transfer was successful.
    pt = update_payin_transfer(db, pt.id, tr.id, 'succeeded', None)
    update_transfer_metadata(tr, pt)
    return pt


def refund_payin(db, payin, refund_amount=None):
    """Create a Charge Refund.

    Args:
        payin (Record): a row from the `payins` table
        refund_amount (Money): the amount of the refund

    Returns:
        Record: the row updated in the `payins` table

    """
    assert payin.status == 'succeeded', "can't refund an unsuccessful charge"
    if refund_amount is None:
        refund_amount = payin.amount - (payin.refunded_amount or 0)
    assert refund_amount >= 0, f"expected a positive amount, got {refund_amount!r}"
    new_refunded_amount = refund_amount + (payin.refunded_amount or 0)
    refund = stripe.Refund.create(
        charge=payin.remote_id,
        amount=Money_to_int(refund_amount),
        idempotency_key=f'refund_{Money_to_int(refund_amount)}_from_payin_{payin.id}',
    )
    rf_amount = int_to_Money(refund.amount, refund.currency)
    assert rf_amount == refund_amount, f"{rf_amount} != {refund_amount}"
    rf_reason = REFUND_REASONS_MAP[refund.reason]
    rf_description = getattr(refund, 'description', None)
    record_payin_refund(
        db, payin.id, refund.id, rf_amount, rf_reason, rf_description,
        refund.status, error=getattr(refund, 'failure_reason', None),
        ctime=(EPOCH + timedelta(seconds=refund.created)),
    )
    assert refund.status in ('pending', 'succeeded'), \
        f"refund {refund.id} has unexpected status {refund.status!r}"
    return update_payin(
        db, payin.id, payin.remote_id, payin.status, payin.error,
        refunded_amount=new_refunded_amount,
    )


def reverse_transfer(db, pt, reversal_amount=None, payin_refund_id=None, idempotency_key=None):
    """Create a Transfer Reversal.

    Args:
        pt (Record): a row from the `payin_transfers` table
        reversal_amount (Money): the amount of the reversal
        payin_refund_id (int): the ID of the parent refund in our database
        idempotency_key (str): the unique identifier of this reversal request

    Returns:
        Record: the row updated in the `payin_transfers` table

    """
    assert pt.status == 'succeeded', "can't reverse an unsuccessful transfer"
    if reversal_amount is None:
        reversal_amount = pt.amount - (pt.reversed_amount or 0)
    assert reversal_amount >= 0, f"expected a positive amount, got {reversal_amount!r}"
    new_reversed_amount = reversal_amount + (pt.reversed_amount or 0)
    if pt.remote_id and reversal_amount > 0:
        try:
            reversal = stripe.Transfer.create_reversal(
                pt.remote_id,
                amount=Money_to_int(reversal_amount),
                idempotency_key=(
                    idempotency_key or
                    f'reverse_{Money_to_int(reversal_amount)}_from_pt_{pt.id}'
                )
            )
        except stripe.error.InvalidRequestError as e:
            if str(e).endswith(" is already fully reversed."):
                return update_payin_transfer(
                    db, pt.id, pt.remote_id, pt.status, pt.error,
                    reversed_amount=pt.amount,
                )
            else:
                raise
        else:
            record_payin_transfer_reversal(
                db, pt.id, reversal.id, reversal_amount, payin_refund_id=payin_refund_id,
                ctime=(EPOCH + timedelta(seconds=reversal.created)),
            )
    return update_payin_transfer(
        db, pt.id, pt.remote_id, pt.status, pt.error, reversed_amount=new_reversed_amount
    )


def sync_transfer(db, pt):
    """Fetch the transfer's data and update our database.

    Args:
        pt (Record): a row from the `payin_transfers` table

    Returns:
        Record: the row updated in the `payin_transfers` table

    """
    assert pt.remote_id, "can't sync a transfer lacking a `remote_id`"
    tr = stripe.Transfer.retrieve(pt.remote_id)
    update_transfer_metadata(tr, pt)
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
        update_transfer_metadata(tr, pt)
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


def update_transfer_metadata(tr, pt):
    """Set `description` and `metadata` if they're missing.

    Args:
        tr (Transfer): the `stripe.Transfer` object to update
        pt (Record): the row from the `payin_transfers` table

    """
    attrs = {}
    if not getattr(tr, 'description', None):
        attrs['description'] = generate_transfer_description(pt)
    if not getattr(tr, 'metadata', None):
        attrs['metadata'] = {'payin_transfer_id': pt.id}
    if attrs:
        try:
            tr = tr.modify(tr.id, **attrs)
        except Exception as e:
            website.tell_sentry(e)
            return tr
    if getattr(tr, 'destination_payment', None):
        py = tr.destination_payment
        if isinstance(py, str):
            try:
                py = stripe.Charge.retrieve(py, stripe_account=tr.destination)
            except Exception as e:
                website.tell_sentry(e)
                return tr
        attrs = {}
        if not getattr(py, 'description', None):
            attrs['description'] = tr.description
        metadata = getattr(py, 'metadata', None) or {}
        if 'liberapay_transfer_id' not in metadata:
            metadata['liberapay_transfer_id'] = pt.id
            attrs['metadata'] = metadata
        if attrs:
            attrs['stripe_account'] = tr.destination
            try:
                py.modify(py.id, **attrs)
            except Exception as e:
                website.tell_sentry(e)
    return tr


def generate_charge_description(payin):
    """Generate the `stripe.Charge.description` value for the given payin.

    For now this function always returns the same string regardless of the payin.
    """
    return "Liberapay"


def generate_transfer_description(pt):
    """Generate the `stripe.Transfer.description` value for the given payin transfer.
    """
    name = website.db.one("""
        SELECT username
          FROM participants
         WHERE id = %s
    """, (pt.team or pt.recipient,))
    if pt.team:
        name = f"team {name}"
    if pt.visibility == 3:
        return f"public donation for {name} via Liberapay"
    if pt.visibility == 2:
        return f"private donation for {name} via Liberapay"
    else:
        return f"secret donation for {name} via Liberapay"


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
