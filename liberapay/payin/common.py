from collections import namedtuple
from datetime import timedelta
from decimal import Decimal

from pando import json
from pando.utils import utcnow
from psycopg2.extras import execute_batch

from ..constants import SEPA
from ..exceptions import (
    AccountSuspended, MissingPaymentAccount, RecipientAccountSuspended,
    NoSelfTipping,
)
from ..i18n.currencies import Money, MoneyBasket
from ..utils import group_by


Donation = namedtuple('Donation', 'amount recipient destination')


def prepare_payin(db, payer, amount, route, off_session=False):
    """Prepare to charge a user.

    Args:
        payer (Participant): the user who will be charged
        amount (Money): the presentment amount of the charge
        route (ExchangeRoute): the payment instrument to charge
        off_session (bool):
            `True` means that the payment is being initiated because it was scheduled,
            `False` means that the payer has initiated the operation just now

    Returns:
        Record: the row created in the `payins` table

    Raises:
        AccountSuspended: if the payer's account is suspended

    """
    assert isinstance(amount, Money), type(amount)
    assert route.participant == payer, (route.participant, payer)
    assert route.status in ('pending', 'chargeable')

    if payer.is_suspended or not payer.get_email_address():
        raise AccountSuspended()

    with db.get_cursor() as cursor:
        payin = cursor.one("""
            INSERT INTO payins
                   (payer, amount, route, status, off_session)
            VALUES (%s, %s, %s, 'pre', %s)
         RETURNING *
        """, (payer.id, amount, route.id, off_session))
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
            UPDATE payins
               SET status = %(status)s
                 , error = %(error)s
                 , remote_id = coalesce(remote_id, %(remote_id)s)
                 , amount_settled = coalesce(amount_settled, %(amount_settled)s)
                 , fee = coalesce(fee, %(fee)s)
                 , intent_id = coalesce(intent_id, %(intent_id)s)
                 , refunded_amount = coalesce(%(refunded_amount)s, refunded_amount)
             WHERE id = %(payin_id)s
         RETURNING *
                 , (SELECT status FROM payins WHERE id = %(payin_id)s) AS old_status
        """, locals())
        if not payin:
            return
        if remote_id and payin.remote_id != remote_id:
            raise AssertionError(f"the remote IDs don't match: {payin.remote_id!r} != {remote_id!r}")

        if status != payin.old_status:
            cursor.run("""
                INSERT INTO payin_events
                       (payin, status, error, timestamp)
                VALUES (%s, %s, %s, current_timestamp)
            """, (payin_id, status, error))

        if status in ('pending', 'succeeded'):
            cursor.run("""
                UPDATE exchange_routes
                   SET status = 'consumed'
                 WHERE id = %s
                   AND one_off IS TRUE
            """, (payin.route,))

        # Lock to avoid concurrent updates
        cursor.run("SELECT * FROM participants WHERE id = %s FOR UPDATE",
                   (payin.payer,))

        # Update scheduled payins, if appropriate
        if status in ('pending', 'succeeded'):
            sp = cursor.one("""
                SELECT *
                  FROM scheduled_payins
                 WHERE payer = %s
                   AND payin = %s
            """, (payin.payer, payin.id))
            if not sp:
                schedule = cursor.all("""
                    SELECT *
                      FROM scheduled_payins
                     WHERE payer = %s
                       AND payin IS NULL
                """, (payin.payer,))
                today = utcnow().date()
                schedule.sort(key=lambda sp: abs((sp.execution_date - today).days))
                payin_tippees = set(cursor.all("""
                    SELECT coalesce(team, recipient) AS tippee
                      FROM payin_transfers
                     WHERE payer = %s
                       AND payin = %s
                """, (payin.payer, payin.id)))
                for sp in schedule:
                    matching_tippees_count = 0
                    other_transfers = []
                    for tr in sp.transfers:
                        if tr['tippee_id'] in payin_tippees:
                            matching_tippees_count += 1
                        else:
                            other_transfers.append(tr)
                    if matching_tippees_count > 0:
                        if other_transfers:
                            cursor.run("""
                                UPDATE scheduled_payins
                                   SET payin = %s
                                     , mtime = current_timestamp
                                 WHERE id = %s
                            """, (payin.id, sp.id))
                            other_transfers_sum = Money.sum(
                                (Money(**tr['amount']) for tr in other_transfers),
                                sp['amount'].currency
                            ) if sp['amount'] else None
                            cursor.run("""
                                INSERT INTO scheduled_payins
                                            (ctime, mtime, execution_date, payer,
                                             amount, transfers, automatic,
                                             notifs_count, last_notif_ts,
                                             customized, payin)
                                     VALUES (%(ctime)s, now(), %(execution_date)s, %(payer)s,
                                             %(amount)s, %(transfers)s, %(automatic)s,
                                             %(notifs_count)s, %(last_notif_ts)s,
                                             %(customized)s, NULL)
                            """, dict(
                                sp._asdict(),
                                amount=other_transfers_sum,
                                transfers=json.dumps(other_transfers),
                            ))
                        else:
                            cursor.run("""
                                UPDATE scheduled_payins
                                   SET payin = %s
                                     , mtime = current_timestamp
                                 WHERE id = %s
                            """, (payin.id, sp.id))
                        break
        elif status == 'failed':
            cursor.run("""
                UPDATE scheduled_payins
                   SET payin = NULL
                 WHERE payer = %s
                   AND payin = %s
            """, (payin.payer, payin.id))

        return payin


def adjust_payin_transfers(db, payin, net_amount):
    """Correct a payin's transfers once the net amount is known.

    Args:
        payin (Record): a row from the `payins` table
        net_amount (Money): the amount of money available to transfer

    """
    payer = db.Participant.from_id(payin.payer)
    route = db.ExchangeRoute.from_id(payer, payin.route)
    provider = route.network.split('-', 1)[0]
    payer_country = route.country
    # We have to update the transfer amounts in a single transaction to
    # avoid ending up in an inconsistent state.
    with db.get_cursor() as cursor:
        payin_transfers = cursor.all("""
            SELECT pt.id, pt.amount, pt.status, pt.remote_id, pt.team, pt.recipient, team_p
              FROM payin_transfers pt
         LEFT JOIN participants team_p ON team_p.id = pt.team
             WHERE pt.payin = %s
          ORDER BY pt.id
               FOR UPDATE OF pt
        """, (payin.id,))
        assert payin_transfers
        if all(pt.status == 'succeeded' for pt in payin_transfers):
            # It's too late to adjust anything.
            return
        transfers_by_tippee = group_by(
            payin_transfers, lambda pt: (pt.team or pt.recipient)
        )
        prorated_amounts = resolve_amounts(net_amount, {
            tippee: MoneyBasket(pt.amount for pt in grouped).fuzzy_sum(net_amount.currency)
            for tippee, grouped in transfers_by_tippee.items()
        })
        teams = set(pt.team for pt in payin_transfers if pt.team is not None)
        updates = []
        for tippee, prorated_amount in prorated_amounts.items():
            transfers = transfers_by_tippee[tippee]
            if tippee in teams:
                team = transfers[0].team_p
                tip = payer.get_tip_to(team)
                try:
                    team_donations = resolve_team_donation(
                        db, team, provider, payer, payer_country,
                        prorated_amount, tip.amount, sepa_only=True,
                    )
                except (MissingPaymentAccount, NoSelfTipping):
                    team_amounts = resolve_amounts(prorated_amount, {
                        pt.id: pt.amount.convert(prorated_amount.currency)
                        for pt in transfers
                    })
                    for pt in transfers:
                        if pt.amount != team_amounts.get(pt.id):
                            assert pt.remote_id is None and pt.status in ('pre', 'pending')
                            updates.append((team_amounts[pt.id], pt.id))
                else:
                    team_donations = {d.recipient.id: d for d in team_donations}
                    for pt in transfers:
                        if pt.status == 'failed':
                            continue
                        d = team_donations.pop(pt.recipient, None)
                        if d is None:
                            assert pt.remote_id is None and pt.status in ('pre', 'pending')
                            cursor.run("""
                                DELETE FROM payin_transfer_events
                                 WHERE payin_transfer = %(pt_id)s
                                   AND status = 'pending';
                                DELETE FROM payin_transfers WHERE id = %(pt_id)s;
                            """, dict(pt_id=pt.id))
                        elif pt.amount != d.amount:
                            assert pt.remote_id is None and pt.status in ('pre', 'pending')
                            updates.append((d.amount, pt.id))
                    n_periods = prorated_amount / tip.periodic_amount.convert(prorated_amount.currency)
                    for d in team_donations.values():
                        unit_amount = (d.amount / n_periods).round_up()
                        prepare_payin_transfer(
                            db, payin, d.recipient, d.destination, 'team-donation',
                            d.amount, unit_amount, tip.period,
                            team=team.id
                        )
            else:
                pt = transfers[0]
                if pt.amount != prorated_amount:
                    assert pt.remote_id is None and pt.status in ('pre', 'pending')
                    updates.append((prorated_amount, pt.id))
        if updates:
            execute_batch(cursor, """
                UPDATE payin_transfers
                   SET amount = %s
                 WHERE id = %s
                   AND status <> 'succeeded';
            """, updates)


def prepare_donation(
    db, payin, tip, tippee, provider, payer, payer_country, payment_amount,
    sepa_only=False,
):
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
        AccountSuspended: if the payer's account is suspended
        MissingPaymentAccount: if no suitable destination has been found
        NoSelfTipping: if the donor would end up sending money to themself
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
            db, tippee, provider, payer, payer_country, payment_amount, tip.amount,
            sepa_only=sepa_only
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
    db, team, provider, payer, payer_country, payment_amount, weekly_amount,
    sepa_only=False,
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
        RecipientAccountSuspended: if the team or all of its members are suspended

    """
    if team.is_suspended:
        raise RecipientAccountSuspended(team)
    currency = payment_amount.currency
    members = team.get_current_takes_for_payment(currency, provider, weekly_amount)
    if all(m.is_suspended for m in members):
        raise RecipientAccountSuspended(members)
    members = [m for m in members if m.has_payment_account and not m.is_suspended]
    if not members:
        raise MissingPaymentAccount(team)
    members = sorted(members, key=lambda t: (
        int(t.member == payer.id),
        -(
            (t.amount + t.takes_sum) /
            (t.received_sum + payment_amount)
        ),
        t.received_sum,
        t.ctime
    ))
    if members[0].member == payer.id:
        raise NoSelfTipping()
    # Try to distribute the donation to multiple members.
    other_members = set(t.member for t in members if t.member != payer.id)
    if sepa_only or other_members and provider == 'stripe':
        sepa_accounts = {a.participant: a for a in db.all("""
            SELECT DISTINCT ON (a.participant) a.*
              FROM payment_accounts a
             WHERE a.participant IN %(members)s
               AND a.provider = 'stripe'
               AND a.is_current
               AND a.country IN %(SEPA)s
          ORDER BY a.participant
                 , a.default_currency = %(currency)s DESC
                 , a.connection_ts
        """, dict(members=other_members, SEPA=SEPA, currency=currency))}
        if sepa_only or len(sepa_accounts) > 1 and members[0].member in sepa_accounts:
            selected_takes = [
                t for t in members if t.member in sepa_accounts and t.amount != 0
            ]
            if selected_takes:
                resolve_take_amounts(payment_amount, selected_takes)
                selected_takes.sort(key=lambda t: t.member)
                return [
                    Donation(
                        t.resolved_amount,
                        db.Participant.from_id(t.member),
                        sepa_accounts[t.member]
                    )
                    for t in selected_takes if t.resolved_amount != 0
                ]
            elif sepa_only:
                raise MissingPaymentAccount(team)
    # Fall back to sending the entire donation to the member who "needs" it most.
    member = db.Participant.from_id(members[0].member)
    account = resolve_destination(db, member, provider, payer, payer_country, payment_amount)
    return [Donation(payment_amount, member, account)]


def resolve_take_amounts(payment_amount, takes):
    """Compute team transfer amounts.

    Args:
        payment_amount (Money): the total amount of money to transfer
        takes (list): rows returned by `team.get_current_takes_for_payment(...)`

    This function doesn't return anything, instead it mutates the given takes,
    adding a `resolved_amount` attribute to each one.

    """
    exp = Decimal('0.7')
    max_weeks_of_advance = 0
    for t in takes:
        if t.amount == 0:
            t.weeks_of_advance = 0
            continue
        t.weeks_of_advance = (t.received_sum - t.takes_sum) / t.amount
        if t.weeks_of_advance < -1:
            # Dampen the effect of past takes, because they can't be changed.
            t.weeks_of_advance = -((-t.weeks_of_advance) ** exp)
        elif t.weeks_of_advance > max_weeks_of_advance:
            max_weeks_of_advance = t.weeks_of_advance
    base_amounts = {t.member: t.amount for t in takes}
    convergence_amounts = {
        t.member: (
            t.amount * (max_weeks_of_advance - t.weeks_of_advance)
        ).round_up()
        for t in takes
    }
    tr_amounts = resolve_amounts(payment_amount, base_amounts, convergence_amounts)
    for t in takes:
        t.resolved_amount = tr_amounts.get(t.member, payment_amount.zero())


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
            UPDATE payin_transfers
               SET status = %(status)s
                 , error = %(error)s
                 , remote_id = coalesce(remote_id, %(remote_id)s)
                 , amount = COALESCE(%(amount)s, amount)
                 , fee = COALESCE(%(fee)s, fee)
                 , reversed_amount = coalesce(%(reversed_amount)s, reversed_amount)
             WHERE id = %(pt_id)s
         RETURNING *
                 , (SELECT amount FROM payin_transfers WHERE id = %(pt_id)s) AS old_amount
                 , (SELECT reversed_amount FROM payin_transfers WHERE id = %(pt_id)s) AS old_reversed_amount
                 , (SELECT status FROM payin_transfers WHERE id = %(pt_id)s) AS old_status
        """, locals())
        if not pt:
            return
        if remote_id and pt.remote_id != remote_id:
            raise AssertionError(f"the remote IDs don't match: {pt.remote_id!r} != {remote_id!r}")

        if status != pt.old_status:
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
        params['delta'] = pt.amount
        if pt.old_status == 'succeeded':
            params['delta'] -= pt.old_amount
        if pt.reversed_amount:
            params['delta'] += -(pt.reversed_amount - (pt.old_reversed_amount or 0))
        if params['delta'] == 0:
            return pt
        updated_tips = cursor.all("""
            WITH latest_tip AS (
                     SELECT *
                       FROM tips
                      WHERE tipper = %(payer)s
                        AND tippee = COALESCE(%(team)s, %(recipient)s)
                   ORDER BY mtime DESC
                      LIMIT 1
                 )
            UPDATE tips t
               SET paid_in_advance = (
                       coalesce_currency_amount(t.paid_in_advance, t.amount::currency) +
                       convert(%(delta)s, t.amount::currency)
                   )
                 , is_funded = true
              FROM latest_tip lt
             WHERE t.tipper = lt.tipper
               AND t.tippee = lt.tippee
               AND t.mtime >= lt.mtime
         RETURNING t.*
        """, params)
        if not updated_tips:
            # This transfer isn't linked to a tip.
            return pt
        assert len(updated_tips) < 10, updated_tips
        if any(t.paid_in_advance <= 0 for t in updated_tips):
            cursor.run("""
                UPDATE tips
                   SET is_funded = false
                 WHERE tipper = %(payer)s
                   AND paid_in_advance <= 0
            """, params)

        # If it's a team donation, update the `paid_in_advance` value of the take.
        if pt.context == 'team-donation':
            updated_takes = cursor.all("""
                WITH latest_take AS (
                         SELECT *
                           FROM takes
                          WHERE team = %(team)s
                            AND member = %(recipient)s
                            AND amount IS NOT NULL
                       ORDER BY mtime DESC
                          LIMIT 1
                     )
                UPDATE takes t
                   SET paid_in_advance = (
                           coalesce_currency_amount(lt.paid_in_advance, lt.amount::currency) +
                           convert(%(delta)s, lt.amount::currency)
                       )
                  FROM latest_take lt
                 WHERE t.team = lt.team
                   AND t.member = lt.member
                   AND t.mtime >= lt.mtime
             RETURNING t.id
            """, params)
            assert 0 < len(updated_takes) < 10, params

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

    # Recompute the donor's cached `giving` amount and payment schedule.
    if update_donor:
        donor = db.Participant.from_id(pt.payer)
        donor.update_giving()
        donor.schedule_renewals()

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
        payer = db.Participant.from_id(payin.payer)
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
