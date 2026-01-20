from datetime import timedelta
from decimal import Decimal

import stripe

from ..constants import EPOCH, PAYIN_SETTLEMENT_DELAYS, SEPA
from ..exceptions import MissingPaymentAccount, NextAction, NoSelfTipping
from ..i18n.currencies import Money, ZERO_DECIMAL_CURRENCIES
from ..models.exchange_route import ExchangeRoute
from ..utils import utcnow
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


def int_to_Money(amount, currency):
    currency = currency.upper()
    if currency in ZERO_DECIMAL_CURRENCIES['stripe']:
        return Money(Decimal(amount), currency)
    return Money(Decimal(amount) / 100, currency)


def Money_to_int(m):
    if m.currency in ZERO_DECIMAL_CURRENCIES['stripe']:
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
    if charge.failure_message or charge.failure_code:
        if charge.failure_message and charge.failure_code:
            return '%s (code %s)' % (charge.failure_message, charge.failure_code)
        else:
            return charge.failure_message or charge.failure_code
    return ''


def charge(db, payin, payer, route, update_donor=True):
    """Initiate or continue the Charge for the given payin.

    Returns the updated payin, or possibly a new payin.

    """
    assert payin.route == route.id
    transfers = db.all("""
        SELECT pt.*,
               p.marked_as AS recipient_marked_as,
               p.join_time::date::text AS recipient_join_time
          FROM payin_transfers pt
          JOIN participants p On p.id = pt.recipient
         WHERE pt.payin = %(payin)s
    """, dict(payin=payin.id))
    payer_state = (
        'blocked' if payer.is_suspended else
        'invalid' if payer.status != 'active' or not payer.can_be_emailed else
        'okay'
    )
    new_status = None
    if payer_state != 'okay':
        new_status = 'failed'
    elif route.network == 'stripe-sdd':
        five_minutes_ago = utcnow() - timedelta(minutes=5)
        if not (payin.allowed_since and payin.allowed_since < five_minutes_ago):
            for pt in transfers:
                if pt.recipient_marked_as in ('fraud', 'spam'):
                    new_status = 'failed'
                    break
                elif pt.recipient_marked_as in ('okay', 'trusted', 'unsettling'):
                    pass
                elif pt.recipient_join_time >= '2022-12-23':
                    new_status = 'awaiting_review'
    if new_status:
        if new_status == payin.status:
            return payin
        else:
            new_payin_error = 'canceled' if new_status == 'failed' else None
            payin = update_payin(db, payin.id, None, new_status, new_payin_error)
            for i, pt in enumerate(transfers, 1):
                new_transfer_error = (
                    "canceled because the payer's account is blocked"
                    if payer_state == 'blocked' else
                    "canceled because the payer's account is in an invalid state"
                    if payer_state == 'invalid' else
                    "canceled because the destination account is blocked"
                    if pt.recipient_marked_as in ('fraud', 'spam') else
                    "canceled because another destination account is blocked"
                ) if new_status == 'failed' else None
                update_payin_transfer(
                    db, pt.id, None, new_status, new_transfer_error,
                    update_donor=(update_donor and i == len(transfers)),
                )
            return payin
    payin, charge = create_charge(
        db, payin, transfers, payer, statement_descriptor=('Liberapay %i' % payin.id),
        update_donor=update_donor,
    )
    if payin.status == 'failed' and len(transfers) == 1:
        payin, charge = try_other_destinations(
            db, payin, payer, charge, update_donor=update_donor,
        )
    if charge and charge.status == 'failed' and charge.failure_code == 'expired_card':
        route.update_status('expired')
    return payin


def try_other_destinations(db, payin, payer, charge, update_donor=True):
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
            error.startswith("Stripe doesn't currently support ") or
            error.startswith("Your card is not supported. Please use a ")
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
            payin, charge = create_charge(
                db, payin, payin_transfers, payer,
                statement_descriptor=('Liberapay %i' % payin.id),
                update_donor=update_donor,
            )
            del payin_transfers
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


def create_charge(
    db, payin, payin_transfers, payer, statement_descriptor, update_donor=True,
):
    """Try to create and capture a Charge.

    Doc: https://docs.stripe.com/connect/charges

    Destination charges don't have built-in support for processing payments
    "at cost", so we (mis)use transfer reversals to recover the exact amount of
    the Stripe fee.

    """
    assert payer.id == payin.payer
    amount = payin.amount
    route = ExchangeRoute.from_id(payer, payin.route)
    description = generate_charge_description(payin)
    destination = None
    if len(payin_transfers) == 1:
        destination, country = db.one("""
            SELECT id, country
              FROM payment_accounts
             WHERE pk = %s
        """, (payin_transfers[0].destination,))
        if destination == 'acct_1ChyayFk4eGpfLOC':
            # Stripe rejects the charge if the destination is our own account
            destination = None
        elif country in SEPA:
            # Don't use destination charges when we can use separate transfers
            destination = None
        del country
    if payin.intent_id:
        intent = stripe.PaymentIntent.retrieve(payin.intent_id)
    else:
        try:
            params = dict(
                amount=Money_to_int(amount),
                confirm=True,
                currency=amount.currency.lower(),
                customer=route.remote_user_id,
                description=description,
                mandate=route.mandate,
                metadata={'payin_id': payin.id},
                off_session=payin.off_session,
                payment_method=route.address,
                payment_method_types=['sepa_debit' if route.network == 'stripe-sdd' else 'card'],
                return_url=payer.url('giving/pay/stripe/%i' % payin.id),
                statement_descriptor=statement_descriptor,
                idempotency_key='payin_intent_%i' % payin.id,
            )
            if route.network == 'stripe-card':
                params['capture_method'] = 'manual'
            if not route.mandate and not route.one_off and not payin.off_session:
                params['setup_future_usage'] = 'off_session'
            if destination:
                params['on_behalf_of'] = destination
                params['transfer_data'] = {'destination': destination}
            intent = stripe.PaymentIntent.create(**params)
        except stripe.StripeError as e:
            return abort_payin(db, payin, repr_stripe_error(e)), None
        except Exception as e:
            website.tell_sentry(e)
            return abort_payin(db, payin, str(e)), None
    if intent.status == 'requires_action':
        update_payin(db, payin.id, None, 'awaiting_payer_action', None,
                     intent_id=intent.id)
        raise NextAction(intent)
    if intent.last_payment_error:
        return abort_payin(db, payin, intent.last_payment_error.message), None
    charge = intent.charges.data[0]
    if charge.status == 'succeeded' and not charge.captured:
        five_minutes_ago = utcnow() - timedelta(minutes=5)
        if payer.is_suspended:
            if payer.marked_since < five_minutes_ago:
                payin = update_payin(
                    db, payin.id, charge.id, 'failed', 'canceled on suspicion of fraud',
                    intent_id=intent.id,
                )
                intent.cancel(
                    cancellation_reason='fraudulent',
                    idempotency_key=f'cancel_{intent.id}',
                )
                return payin, charge
        else:
            capture = payin.status in ('pre', 'awaiting_payer_action', 'awaiting_review') and (
                charge.outcome.risk_level == 'normal' or
                payin.allowed_by is not None and payin.allowed_since < five_minutes_ago
            )
            if capture:
                try:
                    intent = intent.capture(idempotency_key=f'capture_{intent.id}')
                    charge = intent.charges.data[0]
                except stripe.StripeError as e:
                    return abort_payin(db, payin, repr_stripe_error(e)), None
                except Exception as e:
                    website.tell_sentry(e)
                    return abort_payin(db, payin, str(e)), None
    if destination:
        payin = settle_destination_charge(
            db, payin, charge, payin_transfers[0],
            intent_id=intent.id, update_donor=update_donor,
        )
    else:
        payin = settle_charge_and_transfers(
            db, payin, charge, intent_id=intent.id, update_donor=update_donor,
        )
    send_payin_notification(db, payin, payer, charge, route)
    return payin, charge


def set_up_payment_method(pm, route, payin_amount, return_url):
    """Create a SetupIntent for the given PaymentMethod.
    """
    state = website.state.get()
    request, response = state['request'], state['response']
    if route.network == 'stripe-sdd':
        user_agent = request.headers.get(b'User-Agent', b'')
        try:
            user_agent = user_agent.decode('ascii', 'backslashreplace')
        except UnicodeError:
            raise response.error(400, "User-Agent must be ASCII only")
        mandate_data = {
            "customer_acceptance": {
                "type": "online",
                "accepted_at": int(utcnow().timestamp()),
                "online": {
                    "ip_address": str(request.source),
                    "user_agent": user_agent,
                },
            },
        }
    else:
        mandate_data = None
    si = stripe.SetupIntent.create(
        confirm=True,
        customer=route.remote_user_id,
        mandate_data=mandate_data,
        metadata={"route_id": route.id},
        payment_method=pm.id,
        payment_method_types=[pm.type],
        return_url=return_url,
        single_use=dict(
            amount=Money_to_int(payin_amount),
            currency=payin_amount.currency,
        ) if payin_amount and route.one_off else None,
        usage='on_session' if payin_amount and route.one_off else 'off_session',
        idempotency_key='create_SI_for_route_%i' % route.id,
    )
    mandate_id = si.single_use_mandate or si.mandate
    if mandate_id:
        mandate = stripe.Mandate.retrieve(mandate_id)
        route.set_mandate(mandate_id, mandate.payment_method_details.sepa_debit.reference)
    if si.status == 'requires_action':
        act = si.next_action
        if act.type == 'redirect_to_url':
            raise response.refresh(state, url=act.redirect_to_url.url)
        else:
            raise NotImplementedError(act.type)


def send_payin_notification(db, payin, payer, charge, route):
    """Send the legally required notification for SEPA Direct Debits.
    """
    if route.network == 'stripe-sdd' and charge.status != 'failed':
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
            bank_name=route.get_brand(),
            partial_bank_account_number=route.get_partial_number(),
            mandate_url=route.get_mandate_url(),
            mandate_id=route.get_mandate_reference(),
            mandate_creation_date=route.ctime.date(),
            creditor_identifier=website.app_conf.sepa_creditor_identifier,
            average_settlement_seconds=PAYIN_SETTLEMENT_DELAYS['stripe-sdd'].total_seconds(),
            tippees=tippees,
        )


def settle_charge(db, payin, charge):
    """Handle a charge's status change.
    """
    old_payin = payin
    if charge.destination:
        pt = db.one("SELECT * FROM payin_transfers WHERE payin = %s", (payin.id,))
        payin = settle_destination_charge(db, payin, charge, pt)
    else:
        payin = settle_charge_and_transfers(db, payin, charge)
    notify = (
        payin.status != old_payin.status and
        payin.status in ('failed', 'succeeded') and
        payin.ctime < (utcnow() - timedelta(hours=6))
    )
    if notify:
        payer = db.Participant.from_id(payin.payer)
        payer.notify(
            'payin_' + payin.status,
            payin=payin.__dict__,
            recipient_names=payin.recipient_names,
            provider='Stripe',
            email_unverified_address=True,
            idem_key=str(payin.id),
        )
    return payin


def settle_charge_and_transfers(
    db, payin, charge, intent_id=None, update_donor=True,
):
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
    status = charge.status
    if status == 'succeeded' and not charge.captured:
        status = 'awaiting_review'
    payin = update_payin(
        db, payin.id, charge.id, status, error,
        amount_settled=amount_settled, fee=fee, intent_id=intent_id,
        refunded_amount=refunded_amount,
    )
    del refunded_amount, status

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
    last = len(payin_transfers) - 1
    if charge.captured and charge.status == 'succeeded':
        payer = db.Participant.from_id(payin.payer)
        suspend = payer.is_suspended or not payer.can_be_emailed
        undeliverable_amount = amount_settled.zero()
        for i, pt in enumerate(payin_transfers):
            if suspend:
                if pt.status not in ('failed', 'succeeded'):
                    pt = update_payin_transfer(
                        db, pt.id, None, 'suspended', None,
                        update_donor=(update_donor and i == last),
                    )
            elif pt.remote_id is None:
                if pt.destination_id == 'acct_1ChyayFk4eGpfLOC':
                    pt = update_payin_transfer(
                        db, pt.id, None, charge.status, error,
                        update_donor=(update_donor and i == last),
                    )
                elif pt.status in ('pre', 'awaiting_review', 'pending'):
                    pt = execute_transfer(
                        db, pt, charge.id,
                        update_donor=(update_donor and i == last),
                    )
            else:
                pt = sync_transfer(
                    db, pt,
                    update_donor=(update_donor and i == last),
                )
            if pt.status == 'failed':
                undeliverable_amount += pt.amount
            payin_transfers[i] = pt
        if undeliverable_amount:
            refund_ratio = undeliverable_amount / net_amount
            refund_amount = (payin.amount * refund_ratio).round_up()
            if refund_amount > (payin.refunded_amount or 0):
                route = db.ExchangeRoute.from_id(payer, payin.route)
                if route.network == 'stripe-sdd':
                    raise NotImplementedError(
                        "refunds of SEPA direct debits are dangerous"
                    )
                try:
                    payin = refund_payin(db, payin, refund_amount=refund_amount)
                except Exception as e:
                    website.tell_sentry(e)
        if payin.refunded_amount == payin.amount and payin.ctime.year >= 2021:
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
                        db, pt, payin_refund_id=payin_refund_id,
                        update_donor=(update_donor and i == last),
                    )

    else:
        for i, pt in enumerate(payin_transfers):
            update_payin_transfer(
                db, pt.id, None, payin.status, error,
                update_donor=(update_donor and i == last),
            )

    return payin


def execute_transfer(db, pt, source_transaction, update_donor=True):
    """Create a Transfer.

    Args:
        pt (Record): a row from the `payin_transfers` table
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
            destination=pt.destination_id,
            metadata={'payin_transfer_id': pt.id},
            source_transaction=source_transaction,
            idempotency_key='payin_transfer_%i' % pt.id,
        )
    except stripe.StripeError as e:
        error = repr_stripe_error(e)
        if error.startswith("No such destination: "):
            db.run("""
                UPDATE payment_accounts
                   SET is_current = null
                 WHERE provider = 'stripe'
                   AND id = %s
            """, (pt.destination_id,))
            alternate_destination = db.one("""
                SELECT id, pk
                  FROM payment_accounts
                 WHERE participant = %(p_id)s
                   AND provider = 'stripe'
                   AND is_current
                   AND charges_enabled
                   AND country IN %(SEPA)s
              ORDER BY default_currency = %(currency)s DESC
                     , connection_ts
                 LIMIT 1
            """, dict(p_id=pt.recipient, SEPA=SEPA, currency=pt.amount.currency))
            if alternate_destination:
                pt = db.one("""
                    UPDATE payin_transfers
                       SET destination = %s
                     WHERE id = %s
                 RETURNING *
                """, (alternate_destination.pk, pt.id))
                pt.destination_id = alternate_destination.id
                return execute_transfer(db, pt, source_transaction)
            error = "The recipient's account no longer exists."
            return update_payin_transfer(
                db, pt.id, None, 'failed', error, update_donor=update_donor,
            )
        else:
            website.tell_sentry(e, allow_reraise=False)
            return update_payin_transfer(
                db, pt.id, None, 'pending', error, update_donor=update_donor,
            )
    except Exception as e:
        website.tell_sentry(e)
        return update_payin_transfer(
            db, pt.id, None, 'pending', str(e), update_donor=update_donor,
        )
    # `Transfer` objects don't have a `status` attribute, so if no exception was
    # raised we assume that the transfer was successful.
    destination_amount = update_transfer_metadata(tr, pt)
    pt = update_payin_transfer(
        db, pt.id, tr.id, 'succeeded', None, destination_amount=destination_amount,
        update_donor=update_donor,
    )
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


def reverse_transfer(
    db, pt, reversal_amount=None, payin_refund_id=None, idempotency_key=None,
    update_donor=True,
):
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
        except stripe.InvalidRequestError as e:
            if str(e).endswith(" is already fully reversed."):
                return update_payin_transfer(
                    db, pt.id, pt.remote_id, pt.status, pt.error,
                    reversed_amount=pt.amount, update_donor=update_donor,
                )
            else:
                raise
        else:
            record_payin_transfer_reversal(
                db, pt.id, reversal.id, reversal_amount, payin_refund_id=payin_refund_id,
                ctime=(EPOCH + timedelta(seconds=reversal.created)),
            )
    return update_payin_transfer(
        db, pt.id, pt.remote_id, pt.status, pt.error, reversed_amount=new_reversed_amount,
        update_donor=update_donor,
    )


def sync_transfer(db, pt, update_donor=True):
    """Fetch the transfer's data and update our database.

    Args:
        pt (Record): a row from the `payin_transfers` table

    Returns:
        Record: the row updated in the `payin_transfers` table

    """
    assert pt.remote_id, "can't sync a transfer lacking a `remote_id`"
    tr = stripe.Transfer.retrieve(pt.remote_id)
    destination_amount = update_transfer_metadata(tr, pt)
    if tr.amount_reversed:
        reversed_amount = min(int_to_Money(tr.amount_reversed, tr.currency), pt.amount)
    else:
        reversed_amount = None
    record_reversals(db, pt, tr)
    return update_payin_transfer(
        db, pt.id, tr.id, 'succeeded', None, destination_amount=destination_amount,
        reversed_amount=reversed_amount, update_donor=update_donor,
    )


def settle_destination_charge(
    db, payin, charge, pt, intent_id=None, update_donor=True,
):
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
    if status == 'succeeded' and not charge.captured:
        status = 'awaiting_review'
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

    destination_amount = reversed_amount = None
    if getattr(charge, 'transfer', None):
        tr = stripe.Transfer.retrieve(charge.transfer)
        destination_amount = update_transfer_metadata(tr, pt)
        if tr.amount_reversed < bt.fee:
            try:
                tr.reversals.create(
                    amount=bt.fee,
                    description="Stripe fee",
                    metadata={'payin_id': payin.id},
                    idempotency_key='payin_fee_%i' % payin.id,
                )
            except stripe.StripeError as e:
                # In some cases Stripe can refuse to create a reversal. This is
                # a serious problem, it means that Liberapay is losing money,
                # but it can't be properly resolved automatically, so here the
                # error is merely sent to Sentry.
                website.tell_sentry(e)
        elif tr.amount_reversed > bt.fee:
            reversed_amount = int_to_Money(tr.amount_reversed, tr.currency) - fee
            record_reversals(db, pt, tr)

    pt_remote_id = getattr(charge, 'transfer', None)
    pt = update_payin_transfer(
        db, pt.id, pt_remote_id, status, error, amount=net_amount,
        destination_amount=destination_amount, reversed_amount=reversed_amount,
        update_donor=update_donor,
    )

    return payin


def update_transfer_metadata(tr, pt):
    """Set `description` and `metadata` if they're missing.

    Args:
        tr (Transfer): the `stripe.Transfer` object to update
        pt (Record): the row from the `payin_transfers` table

    Returns the amount actually credited to the destination account, which may
    be in a different currency than the Transfer amount.

    """
    attrs = {}
    if not getattr(tr, 'description', None):
        attrs['description'] = generate_transfer_description(pt)
    if not getattr(tr, 'metadata', None):
        attrs['metadata'] = {'payin_transfer_id': pt.id}
    if attrs:
        try:
            tr.modify(tr.id, **attrs)
        except Exception as e:
            website.tell_sentry(e)
            return tr
    if getattr(tr, 'destination_payment', None):
        try:
            py = stripe.Charge.retrieve(
                tr.destination_payment,
                expand=['balance_transaction'],
                stripe_account=tr.destination,
            )
        except stripe.PermissionError as e:
            if str(e).endswith(" Application access may have been revoked."):
                pass
            else:
                website.tell_sentry(e)
            return None
        except Exception as e:
            website.tell_sentry(e)
            return None
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
            except stripe.PermissionError as e:
                if str(e).endswith(" Application access may have been revoked."):
                    pass
                else:
                    website.tell_sentry(e)
            except Exception as e:
                website.tell_sentry(e)
        destination_amount = None
        bt = py.balance_transaction
        if bt:
            destination_amount = int_to_Money(bt.amount, bt.currency)
        return destination_amount
    else:
        return None


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
