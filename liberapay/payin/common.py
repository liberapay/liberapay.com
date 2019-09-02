from datetime import timedelta
from decimal import Decimal

from pando.utils import utcnow
from psycopg2.extras import execute_batch

from ..constants import SEPA
from ..exceptions import (
    AccountSuspended, MissingPaymentAccount, RecipientAccountSuspended,
    NoSelfTipping,
)
from ..i18n.currencies import Money, MoneyBasket
from ..models.exchange_route import ExchangeRoute
from ..models.participant import Participant
from ..utils import NS, group_by


class Donation(object):

    __slots__ = ('amount', 'recipient', 'destination')

    def __init__(self, amount, recipient, destination):
        assert destination.participant == recipient.id
        self.amount = amount
        self.recipient = recipient
        self.destination = destination


def prepare_payin(db, payer, amount, route):
    """Prepare to charge a user.

    Args:
        payer (Participant): the user who will be charged
        amount (Money): the presentment amount of the charge
        route (ExchangeRoute): the payment instrument to charge

    Returns:
        Record: the row created in the `payins` table

    Raises:
        AccountSuspended: if the payer's account is suspended

    """
    assert isinstance(amount, Money), type(amount)
    assert route.participant == payer, (route.participant, payer)
    assert route.status in ('pending', 'chargeable')

    if payer.is_suspended:
        raise AccountSuspended()

    with db.get_cursor() as cursor:
        payin = cursor.one("""
            INSERT INTO payins
                   (payer, amount, route, status)
            VALUES (%s, %s, %s, 'pre')
         RETURNING *
        """, (payer.id, amount, route.id))
        cursor.run("""
            INSERT INTO payin_events
                   (payin, status, error, timestamp)
            VALUES (%s, %s, NULL, current_timestamp)
        """, (payin.id, payin.status))

    return payin


def update_payin(
    db, payin_id, remote_id, status, error,
    amount_settled=None, fee=None, intent_id=None, refunded_amount=None,
):
    """Update the status and other attributes of a charge.

    Args:
        payin_id (int): the ID of the charge in our database
        remote_id (str): the ID of the charge in the payment processor's database
        status (str): the new status of the charge
        error (str): if the charge failed, an error message to show to the payer

    Returns:
        Record: the row updated in the `payins` table

    """
    with db.get_cursor() as cursor:
        payin = cursor.one("""
            WITH old AS (
                SELECT * FROM payins WHERE id = %(payin_id)s
            )
            UPDATE payins
               SET status = %(status)s
                 , error = %(error)s
                 , remote_id = coalesce(%(remote_id)s, remote_id)
                 , amount_settled = COALESCE(%(amount_settled)s, amount_settled)
                 , fee = COALESCE(%(fee)s, fee)
                 , intent_id = coalesce(%(intent_id)s, intent_id)
                 , refunded_amount = coalesce(%(refunded_amount)s, refunded_amount)
             WHERE id = %(payin_id)s
               AND ( status <> %(status)s OR
                     coalesce_currency_amount(%(refunded_amount)s, amount::currency) <>
                     coalesce_currency_amount(refunded_amount, amount::currency)
                   )
         RETURNING *
                 , (SELECT status FROM old) AS old_status
        """, locals())
        if not payin:
            return cursor.one("SELECT * FROM payins WHERE id = %s", (payin_id,))

        if payin.status != payin.old_status:
            cursor.run("""
                INSERT INTO payin_events
                       (payin, status, error, timestamp)
                VALUES (%s, %s, %s, current_timestamp)
            """, (payin_id, status, error))

        if payin.status in ('pending', 'succeeded'):
            cursor.run("""
                UPDATE exchange_routes
                   SET status = 'consumed'
                 WHERE id = %s
                   AND one_off IS TRUE
            """, (payin.route,))

        return payin


def adjust_payin_transfers(db, payin, net_amount):
    """Correct a payin's transfers once the net amount is known.

    Args:
        payin (Record): a row from the `payins` table
        net_amount (Money): the amount of money available to transfer

    """
    payer = Participant.from_id(payin.payer)
    route = ExchangeRoute.from_id(payer, payin.route)
    provider = route.network.split('-', 1)[0]
    payer_country = route.country
    # We have to update the transfer amounts in a single transaction to
    # avoid ending up in an inconsistent state.
    with db.get_cursor() as cursor:
        payin_transfers = cursor.all("""
            SELECT pt.id, pt.amount, pt.team, pt.recipient, team_p
              FROM payin_transfers pt
         LEFT JOIN participants team_p ON team_p.id = pt.team
             WHERE pt.payin = %s
          ORDER BY pt.id
               FOR UPDATE OF pt
        """, (payin.id,))
        assert payin_transfers
        transfers_by_tippee = group_by(
            payin_transfers, lambda pt: (pt.team or pt.recipient)
        )
        prorated_amounts = resolve_amounts(net_amount, {
            tippee: MoneyBasket(pt.amount for pt in grouped).fuzzy_sum(net_amount.currency)
            for tippee, grouped in transfers_by_tippee.items()
        })
        updates = []
        for tippee, prorated_amount in prorated_amounts.items():
            transfers = transfers_by_tippee[tippee]
            if len(transfers) > 1:
                team = transfers[0].team_p
                tip = payer.get_tip_to(team)
                try:
                    team_donations = resolve_team_donation(
                        cursor, team, provider, payer, payer_country,
                        prorated_amount, tip['amount']
                    )
                except (MissingPaymentAccount, NoSelfTipping):
                    team_amounts = resolve_amounts(prorated_amount, {
                        pt.id: pt.amount.convert(prorated_amount.currency)
                        for pt in transfers
                    })
                    for pt in transfers:
                        if pt.amount != team_amounts.get(pt.id):
                            updates.append((team_amounts[pt.id], pt.id))
                else:
                    team_donations = {d.recipient.id: d for d in team_donations}
                    for pt in transfers:
                        d = team_donations.pop(pt.recipient, None)
                        if d is None:
                            assert pt.status == 'pre'
                            cursor.run("DELETE FROM payin_transfers WHERE id = %s", (pt.id,))
                        elif pt.amount != d.amount:
                            updates.append((d.amount, pt.id))
                    for d in team_donations.values():
                        prepare_payin_transfer(
                            db, payin, d.recipient, d.destination, 'team-donation',
                            d.amount, tip['periodic_amount'], tip['period'],
                            team=team.id
                        )
            else:
                pt = transfers[0]
                if pt.amount != prorated_amount:
                    updates.append((prorated_amount, pt.id))
        if updates:
            execute_batch(cursor, """
                UPDATE payin_transfers
                   SET amount = %s
                 WHERE id = %s
                   AND status <> 'succeeded';
            """, updates)


def prepare_donation(db, payin, tip, tippee, provider, payer, payer_country, payment_amount):
    """Prepare to distribute a donation.

    Args:
        payin (Record): a row from the `payins` table
        tip (Record): a row from the `tips` table
        tippee (Participant): the intended beneficiary of the donation
        provider (str): the payment processor ('paypal' or 'stripe')
        payer (Participant): the donor
        payer_country (str): the country the money is supposedly coming from
        payment_amount (Money): the amount of money being sent

    Returns:
        a list of the rows created in the `payin_transfers` table

    Raises:
        MissingPaymentAccount: if no suitable destination has been found
        NoSelfTipping: if the donor would end up sending money to themself

    Raises:
        AccountSuspended: if the payer's account is suspended
        RecipientAccountSuspended: if the tippee's account is suspended

    """
    assert tip.tipper == payer.id
    assert tip.tippee == tippee.id

    if payer.is_suspended:
        raise AccountSuspended(payer)
    if tippee.is_suspended:
        raise RecipientAccountSuspended(tippee)

    r = []
    if tippee.kind == 'group':
        team_donations = resolve_team_donation(
            db, tippee, provider, payer, payer_country, payment_amount, tip.amount
        )
        n_periods = payment_amount / tip.periodic_amount
        for d in team_donations:
            unit_amount = (d.amount / n_periods).round_up()
            r.append(prepare_payin_transfer(
                db, payin, d.recipient, d.destination, 'team-donation',
                d.amount, unit_amount, tip.period, team=tippee.id
            ))
    else:
        destination = resolve_destination(
            db, tippee, provider, payer, payer_country, payment_amount
        )
        r.append(prepare_payin_transfer(
            db, payin, tippee, destination, 'personal-donation',
            payment_amount, tip.periodic_amount, tip.period
        ))
    return r


def resolve_destination(db, tippee, provider, payer, payer_country, payin_amount):
    """Figure out where to send a payment.

    Args:
        tippee (Participant): the intended beneficiary of the payment
        provider (str): the payment processor ('paypal' or 'stripe')
        payer (Participant): the user who wants to pay
        payer_country (str): the country the money is supposedly coming from
        payin_amount (Money): the payment amount

    Returns:
        Record: a row from the `payment_accounts` table

    Raises:
        MissingPaymentAccount: if no suitable destination has been found
        NoSelfTipping: if the payer would end up sending money to themself

    """
    if tippee.id == payer.id:
        raise NoSelfTipping()
    destination = db.one("""
        SELECT *
          FROM payment_accounts
         WHERE participant = %s
           AND provider = %s
           AND is_current
           AND verified
           AND coalesce(charges_enabled, true)
      ORDER BY country = %s DESC
             , default_currency = %s DESC
             , connection_ts
         LIMIT 1
    """, (tippee.id, provider, payer_country, payin_amount.currency))
    if destination:
        return destination
    else:
        raise MissingPaymentAccount(tippee)


def resolve_team_donation(
    db, team, provider, payer, payer_country, payment_amount, weekly_amount
):
    """Figure out how to distribute a donation to a team's members.

    Args:
        team (Participant): the team the donation is for
        provider (str): the payment processor ('paypal' or 'stripe')
        payer (Participant): the donor
        payer_country (str): the country code the money is supposedly coming from
        payment_amount (Money): the amount of money being sent
        weekly_amount (Money): the weekly donation amount

    Returns:
        a list of `Donation` objects

    Raises:
        MissingPaymentAccount: if no suitable destination has been found
        NoSelfTipping: if the payer would end up sending money to themself

    """
    members = [NS(r._asdict()) for r in db.all("""
        SELECT t.member
             , t.ctime
             , t.amount
             , (coalesce_currency_amount((
                   SELECT sum(pt.amount - coalesce(pt.reversed_amount, zero(pt.amount)), 'EUR')
                     FROM payin_transfers pt
                    WHERE pt.recipient = t.member
                      AND pt.team = t.team
                      AND pt.context = 'team-donation'
                      AND pt.status = 'succeeded'
               ), 'EUR') + coalesce_currency_amount((
                   SELECT sum(tr.amount, 'EUR')
                     FROM transfers tr
                    WHERE tr.tippee = t.member
                      AND tr.team = t.team
                      AND tr.context IN ('take', 'take-in-advance')
                      AND tr.status = 'succeeded'
                      AND tr.virtual IS NOT true
               ), 'EUR')) AS received_sum_eur
             , (coalesce_currency_amount((
                   SELECT sum(t2.amount, 'EUR')
                     FROM ( SELECT ( SELECT t2.amount
                                       FROM takes t2
                                      WHERE t2.member = t.member
                                        AND t2.team = t.team
                                        AND t2.mtime < coalesce(
                                                payday.ts_start, current_timestamp
                                            )
                                   ORDER BY t2.mtime DESC
                                      LIMIT 1
                                   ) AS amount
                              FROM paydays payday
                          ) t2
                    WHERE t2.amount > 0
               ), 'EUR')) AS takes_sum_eur
          FROM current_takes t
          JOIN participants p ON p.id = t.member
         WHERE t.team = %s
           AND t.amount <> 0
           AND p.is_suspended IS NOT true
           AND EXISTS (
                   SELECT true
                     FROM payment_accounts a
                    WHERE a.participant = t.member
                      AND a.provider = %s
                      AND a.is_current
                      AND a.verified
                      AND coalesce(a.charges_enabled, true)
               )
    """, (team.id, provider))]
    if not members:
        raise MissingPaymentAccount(team)
    payment_amount_eur = payment_amount.convert('EUR')
    zero_eur = Money.ZEROS['EUR']
    income_amount_eur = team.receiving.convert('EUR') + weekly_amount.convert('EUR')
    if income_amount_eur == 0:
        income_amount_eur = Money.MINIMUMS['EUR']
    manual_takes_sum = MoneyBasket(t.amount for t in members if t.amount > 0)
    auto_take = income_amount_eur - manual_takes_sum.fuzzy_sum('EUR')
    if auto_take < 0:
        auto_take = zero_eur
    for t in members:
        t.amount_eur = auto_take if t.amount < 0 else t.amount.convert('EUR')
    members = sorted(members, key=lambda t: (
        int(t.member == payer.id),
        -(
            (t.amount_eur + t.takes_sum_eur) /
            (t.received_sum_eur + payment_amount_eur)
        ),
        t.received_sum_eur,
        t.ctime
    ))
    # Try to distribute the donation to multiple members.
    if provider == 'stripe':
        other_members = set(t.member for t in members if t.member != payer.id)
        sepa_accounts = {a.participant: a for a in db.all("""
            SELECT DISTINCT ON (a.participant) a.*
              FROM payment_accounts a
             WHERE a.participant IN %(members)s
               AND a.provider = 'stripe'
               AND a.is_current
               AND a.country IN %(SEPA)s
          ORDER BY a.participant
                 , a.default_currency = 'EUR' DESC
                 , a.connection_ts
        """, dict(members=other_members, SEPA=SEPA))} if other_members else ()
        if len(sepa_accounts) > 1 and members[0].member in sepa_accounts:
            exp = Decimal('0.7')
            selected_takes = []
            max_weeks_of_advance = 0
            for t in members:
                if t.member not in sepa_accounts:
                    continue
                t.weeks_of_advance = (t.received_sum_eur - t.takes_sum_eur) / t.amount_eur
                if t.weeks_of_advance < -1:
                    # Dampen the effect of past takes, because they can't be changed.
                    t.weeks_of_advance = -((-t.weeks_of_advance) ** exp)
                elif t.weeks_of_advance > max_weeks_of_advance:
                    max_weeks_of_advance = t.weeks_of_advance
                selected_takes.append(t)
            del members
            base_amounts = {t.member: t.amount_eur for t in selected_takes}
            convergence_amounts = {
                t.member: (
                    t.amount_eur * (max_weeks_of_advance - t.weeks_of_advance)
                ).round_up()
                for t in selected_takes
            }
            tr_amounts = resolve_amounts(payment_amount_eur, base_amounts, convergence_amounts)
            return [
                Donation(tr_amount, Participant.from_id(p_id), sepa_accounts[p_id])
                for p_id, tr_amount in sorted(tr_amounts.items()) if tr_amount != 0
            ]
    # Fall back to sending the entire donation to the member who "needs" it most.
    member = Participant.from_id(members[0].member)
    account = resolve_destination(db, member, provider, payer, payer_country, payment_amount)
    return [Donation(payment_amount, member, account)]


def resolve_amounts(available_amount, base_amounts, convergence_amounts=None):
    """Compute transfer amounts.

    Args:
        available_amount (Money):
            the payin amount to split into transfer amounts
        base_amounts (Dict[Any, Money]):
            a map of IDs to raw transfer amounts
        convergence_amounts (Dict[Any, Money]):
            an optional map of IDs to ideal additional amounts

    Returns a copy of `base_amounts` with updated values.
    """
    min_transfer_amount = Money.MINIMUMS[available_amount.currency]
    r = {}
    amount_left = available_amount

    # Attempt to converge
    if convergence_amounts:
        convergence_sum = Money.sum(convergence_amounts.values(), amount_left.currency)
        if convergence_sum != 0:
            convergence_amounts = {k: v for k, v in convergence_amounts.items() if v != 0}
            if amount_left == convergence_sum:
                # We have just enough money for convergence.
                return convergence_amounts
            elif amount_left > convergence_sum:
                # We have more than enough money for full convergence, the extra
                # funds will be allocated in proportion to `base_amounts`.
                r.update(convergence_amounts)
                amount_left -= convergence_sum
            else:
                # We only have enough for partial convergence, the funds will be
                # allocated in proportion to `convergence_amounts`.
                base_amounts = convergence_amounts

    # Compute the prorated amounts
    base_sum = Money.sum(base_amounts.values(), amount_left.currency)
    base_ratio = amount_left / base_sum
    for key, base_amount in sorted(base_amounts.items()):
        if base_amount == 0:
            continue
        assert amount_left >= min_transfer_amount
        amount = min((base_amount * base_ratio).round_down(), amount_left)
        r[key] = amount + r.get(key, 0)
        amount_left -= amount

    # Deal with rounding errors
    if amount_left > 0:
        # Try to distribute in a way that doesn't skew the percentages much.
        def compute_priority(item):
            key, current_amount = item
            base_amount = base_amounts[key] * base_ratio
            return (current_amount - base_amount) / base_amount

        for key, amount in sorted(r.items(), key=compute_priority):
            r[key] += min_transfer_amount
            amount_left -= min_transfer_amount
            if amount_left == 0:
                break

    # Final check and return
    assert amount_left == 0, '%r != 0' % amount_left
    return r


def prepare_payin_transfer(
    db, payin, recipient, destination, context, amount,
    unit_amount=None, period=None, team=None
):
    """Prepare the allocation of funds from a payin.

    Args:
        payin (Record): a row from the `payins` table
        recipient (Participant): the user who will receive the money
        destination (Record): a row from the `payment_accounts` table
        amount (Money): the amount of money that will be received
        unit_amount (Money): the `periodic_amount` of a recurrent donation
        period (str): the period of a recurrent payment
        team (int): the ID of the project this payment is tied to

    Returns:
        Record: the row created in the `payin_transfers` table

    """
    assert recipient.id == destination.participant, (recipient, destination)

    if recipient.is_suspended:
        raise RecipientAccountSuspended()

    if unit_amount:
        n_units = int(amount / unit_amount.convert(amount.currency))
    else:
        n_units = None
    return db.one("""
        INSERT INTO payin_transfers
               (payin, payer, recipient, destination, context, amount,
                unit_amount, n_units, period, team,
                status)
        VALUES (%s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                'pre')
     RETURNING *
    """, (payin.id, payin.payer, recipient.id, destination.pk, context, amount,
          unit_amount, n_units, period, team))


def update_payin_transfer(
    db, pt_id, remote_id, status, error,
    amount=None, fee=None, update_donor=True, reversed_amount=None,
):
    """Update the status and other attributes of a payment.

    Args:
        pt_id (int): the ID of the payment in our database
        remote_id (str): the ID of the transfer in the payment processor's database
        status (str): the new status of the payment
        error (str): if the payment failed, an error message to show to the payer

    Returns:
        Record: the row updated in the `payin_transfers` table

    """
    with db.get_cursor() as cursor:
        pt = cursor.one("""
            WITH old AS (
                SELECT * FROM payin_transfers WHERE id = %(pt_id)s
            )
            UPDATE payin_transfers
               SET status = %(status)s
                 , error = %(error)s
                 , remote_id = coalesce(%(remote_id)s, remote_id)
                 , amount = COALESCE(%(amount)s, amount)
                 , fee = COALESCE(%(fee)s, fee)
                 , reversed_amount = coalesce(%(reversed_amount)s, reversed_amount)
             WHERE id = %(pt_id)s
               AND ( status <> %(status)s OR
                     coalesce_currency_amount(%(reversed_amount)s, amount::currency) <>
                     coalesce_currency_amount(reversed_amount, amount::currency)
                   )
         RETURNING *
                 , (SELECT reversed_amount FROM old) AS old_reversed_amount
                 , (SELECT status FROM old) AS old_status
        """, locals())
        if not pt:
            return cursor.one("SELECT * FROM payin_transfers WHERE id = %s", (pt_id,))

        if pt.status != pt.old_status:
            cursor.run("""
                INSERT INTO payin_transfer_events
                       (payin_transfer, status, error, timestamp)
                VALUES (%s, %s, %s, current_timestamp)
            """, (pt_id, status, error))

        # If the payment has failed or hasn't been settled yet, then stop here.
        if status != 'succeeded':
            return pt

        # Update the `paid_in_advance` value of the donation.
        params = pt._asdict()
        if pt.reversed_amount:
            params['delta'] = -(pt.reversed_amount - (pt.old_reversed_amount or 0))
            if params['delta'] == 0:
                return pt
        else:
            params['delta'] = pt.amount
        paid_in_advance = cursor.one("""
            WITH current_tip AS (
                     SELECT id
                       FROM current_tips
                      WHERE tipper = %(payer)s
                        AND tippee = COALESCE(%(team)s, %(recipient)s)
                 )
            UPDATE tips
               SET paid_in_advance = (
                       coalesce_currency_amount(paid_in_advance, amount::currency) +
                       convert(%(delta)s, amount::currency)
                   )
                 , is_funded = true
             WHERE id = (SELECT id FROM current_tip)
         RETURNING paid_in_advance
        """, params)
        if paid_in_advance is None:
            # This transfer isn't linked to a tip.
            return pt
        if paid_in_advance <= 0:
            cursor.run("""
                UPDATE tips
                   SET is_funded = false
                 WHERE tipper = %(payer)s
                   AND paid_in_advance <= 0
            """, params)

        # If it's a team donation, update the `paid_in_advance` value of the take.
        if pt.context == 'team-donation':
            paid_in_advance = cursor.one("""
                WITH current_take AS (
                         SELECT id
                           FROM takes
                          WHERE team = %(team)s
                            AND member = %(recipient)s
                       ORDER BY mtime DESC
                          LIMIT 1
                     )
                UPDATE takes
                   SET paid_in_advance = (
                           coalesce_currency_amount(paid_in_advance, amount::currency) +
                           convert(%(delta)s, amount::currency)
                       )
                 WHERE id = (SELECT id FROM current_take)
             RETURNING paid_in_advance
            """, params)
            assert paid_in_advance is not None, locals()

        # Recompute the cached `receiving` amount of the donee.
        cursor.run("""
            WITH our_tips AS (
                     SELECT t.amount
                       FROM current_tips t
                      WHERE t.tippee = %(p_id)s
                        AND t.is_funded
                 )
            UPDATE participants AS p
               SET receiving = taking + coalesce_currency_amount(
                       (SELECT sum(t.amount, p.main_currency) FROM our_tips t),
                       p.main_currency
                   )
                 , npatrons = (SELECT count(*) FROM our_tips)
             WHERE p.id = %(p_id)s
        """, dict(p_id=(pt.team or pt.recipient)))

        # Recompute the cached `giving` amount of the donor.
        if update_donor:
            Participant.from_id(pt.payer).update_giving(cursor)

        return pt


def abort_payin(db, payin, error='aborted by payer'):
    """Mark a payin as cancelled.

    Args:
        payin (Record): a row from the `payins` table
        error (str): the error message to attach to the payin

    Returns:
        Record: the row updated in the `payins` table

    """
    payin = update_payin(db, payin.id, payin.remote_id, 'failed', error)
    db.run("""
        WITH updated_transfers as (
            UPDATE payin_transfers
               SET status = 'failed'
                 , error = %(error)s
             WHERE payin = %(payin_id)s
               AND status <> 'failed'
         RETURNING *
        )
        INSERT INTO payin_transfer_events
                    (payin_transfer, status, error, timestamp)
             SELECT pt.id, 'failed', pt.error, current_timestamp
               FROM updated_transfers pt
    """, dict(error=error, payin_id=payin.id))
    return payin


def record_payin_refund(
    db, payin_id, remote_id, amount, reason, description, status, error=None, ctime=None,
):
    """Record a charge refund.

    Args:
        payin_id (int): the ID of the refunded payin in our database
        remote_id (int): the ID of the refund in the payment processor's database
        amount (Money): the refund amount, must be less or equal to the payin amount
        reason (str): why this refund was initiated (`refund_reason` SQL type)
        description (str): details of the circumstances of this refund
        status (str): the current status of the refund (`refund_status` SQL type)
        error (str): error message, if the refund has failed
        ctime (datetime): when the refund was initiated

    Returns:
        Record: the row inserted in the `payin_refunds` table

    """
    refund = db.one("""
        INSERT INTO payin_refunds
               (payin, remote_id, amount, reason, description,
                status, error, ctime)
        VALUES (%(payin_id)s, %(remote_id)s, %(amount)s, %(reason)s, %(description)s,
                %(status)s, %(error)s, coalesce(%(ctime)s, current_timestamp))
   ON CONFLICT (payin, remote_id) DO UPDATE
           SET amount = excluded.amount
             , reason = excluded.reason
             , description = excluded.description
             , status = excluded.status
             , error = excluded.error
     RETURNING *
             , ( SELECT old.status
                   FROM payin_refunds old
                  WHERE old.payin = %(payin_id)s
                    AND old.remote_id = %(remote_id)s
               ) AS old_status
    """, locals())
    notify = (
        refund.status in ('pending', 'succeeded') and
        refund.status != refund.old_status and
        refund.ctime > (utcnow() - timedelta(hours=24))
    )
    if notify:
        payin = db.one("SELECT * FROM payins WHERE id = %s", (refund.payin,))
        payer = Participant.from_id(payin.payer)
        payer.notify(
            'payin_refund_initiated',
            payin_amount=payin.amount,
            payin_ctime=payin.ctime,
            refund_amount=refund.amount,
            refund_reason=refund.reason,
        )
    return refund


def record_payin_transfer_reversal(
    db, pt_id, remote_id, amount, payin_refund_id=None, ctime=None
):
    """Record a transfer reversal.

    Args:
        pt_id (int): the ID of the reversed transfer in our database
        remote_id (int): the ID of the reversal in the payment processor's database
        amount (Money): the reversal amount, must be less or equal to the transfer amount
        payin_refund_id (int): the ID of the associated payin refund in our database
        ctime (datetime): when the refund was initiated

    Returns:
        Record: the row inserted in the `payin_transfer_reversals` table

    """
    return db.one("""
        INSERT INTO payin_transfer_reversals
               (payin_transfer, remote_id, amount, payin_refund,
                ctime)
        VALUES (%(pt_id)s, %(remote_id)s, %(amount)s, %(payin_refund_id)s,
                coalesce(%(ctime)s, current_timestamp))
   ON CONFLICT (payin_transfer, remote_id) DO UPDATE
           SET amount = excluded.amount
             , payin_refund = excluded.payin_refund
     RETURNING *
    """, locals())
