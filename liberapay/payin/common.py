from collections import namedtuple
from datetime import timedelta
from decimal import ROUND_UP
import itertools
from operator import attrgetter
import warnings

from pando.utils import utcnow
from psycopg2.extras import execute_batch

from ..constants import SEPA
from ..exceptions import (
    AccountSuspended, BadDonationCurrency, EmailRequired, MissingPaymentAccount,
    NoSelfTipping, ProhibitedSourceCountry, RecipientAccountSuspended,
    UnableToDeterminePayerCountry, UserDoesntAcceptTips,
)
from ..i18n.currencies import Money, MoneyBasket
from ..utils import group_by


ProtoTransfer = namedtuple(
    'ProtoTransfer',
    'amount recipient destination context unit_amount period team visibility',
)


def get_minimum_transfer_amount(provider, currency):
    if provider == 'stripe' and currency != 'EUR':
        # Stripe refuses transfers whose amounts are lower than the equivalent
        # of €0.01. Since we don't know the exchange rate they're using, we add
        # a 20% safety margin and round upward.
        return Money('0.012', 'EUR').convert(currency, ROUND_UP)
    return Money.MINIMUMS[currency]


def prepare_payin(db, payer, amount, route, proto_transfers, off_session=False):
    """Prepare to charge a user.

    Args:
        payer (Participant): the user who will be charged
        amount (Money): the presentment amount of the charge
        route (ExchangeRoute): the payment instrument to charge
        proto_transfers ([ProtoTransfer]): the transfers to prepare
        off_session (bool):
            `True` means that the payment is being initiated because it was scheduled,
            `False` means that the payer has initiated the operation just now

    Returns:
        Payin: the row created in the `payins` table

    Raises:
        AccountSuspended: if the payer's account is suspended

    """
    assert isinstance(amount, Money), type(amount)
    assert route.participant == payer, (route.participant, payer)
    assert route.status in ('pending', 'chargeable')

    if payer.is_suspended:
        raise AccountSuspended()
    if not payer.can_be_emailed:
        raise EmailRequired()

    if route.network == 'paypal':
        # The country of origin check for PayPal payments is in the
        # `liberapay.payin.paypal.capture_order` function.
        pass
    else:
        for pt in proto_transfers:
            if (allowed_countries := pt.recipient.recipient_settings.patron_countries):
                if route.country not in allowed_countries:
                    if route.country:
                        raise ProhibitedSourceCountry(pt.recipient, route.country)
                    else:
                        raise UnableToDeterminePayerCountry()

    with db.get_cursor() as cursor:
        payin = cursor.one("""
            INSERT INTO payins
                   (payer, amount, route, status, off_session)
            VALUES (%s, %s, %s, 'pre', %s)
         RETURNING payins
        """, (payer.id, amount, route.id, off_session))
        cursor.run("""
            INSERT INTO payin_events
                   (payin, status, error, timestamp)
            VALUES (%s, %s, NULL, current_timestamp)
        """, (payin.id, payin.status))
        payin_transfers = []
        for t in proto_transfers:
            payin_transfers.append(prepare_payin_transfer(
                cursor, payin, t.recipient, t.destination, t.context, t.amount,
                t.visibility, t.unit_amount, t.period, t.team,
            ))

    return payin, payin_transfers


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
        Payin: the row updated in the `payins` table

    """
    with db.get_cursor() as cursor:
        payin, old_status = cursor.one("""
            UPDATE payins
               SET status = %(status)s
                 , error = %(error)s
                 , remote_id = coalesce(remote_id, %(remote_id)s)
                 , amount_settled = coalesce(amount_settled, %(amount_settled)s)
                 , fee = coalesce(fee, %(fee)s)
                 , intent_id = coalesce(intent_id, %(intent_id)s)
                 , refunded_amount = coalesce(%(refunded_amount)s, refunded_amount)
             WHERE id = %(payin_id)s
         RETURNING payins
                 , (SELECT status FROM payins WHERE id = %(payin_id)s) AS old_status
        """, locals(), default=(None, None))
        if not payin:
            return
        if remote_id and payin.remote_id != remote_id:
            raise AssertionError(f"the remote IDs don't match: {payin.remote_id!r} != {remote_id!r}")

        if status != old_status:
            cursor.run("""
                INSERT INTO payin_events
                       (payin, status, error, timestamp)
                VALUES (%s, %s, %s, current_timestamp)
            """, (payin_id, status, error))

        if status in ('failed', 'pending', 'succeeded'):
            new_route_status = 'failed' if status == 'failed' else 'consumed'
            route = cursor.one("""
                UPDATE exchange_routes
                   SET status = %s
                 WHERE id = %s
                   AND one_off
                   AND status = 'chargeable'
             RETURNING exchange_routes
            """, (new_route_status, payin.route))
            if route:
                route.detach()

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
                # Try to find a scheduled renewal that matches this payin.
                # It doesn't have to be an exact match.
                schedule = cursor.all("""
                    SELECT *
                      FROM scheduled_payins
                     WHERE payer = %s
                       AND payin IS NULL
                       AND mtime < %s
                """, (payin.payer, payin.ctime))
                today = utcnow().date()
                schedule.sort(key=lambda sp: abs((sp.execution_date - today).days))
                payin_tippees = set(cursor.all("""
                    SELECT coalesce(team, recipient) AS tippee
                      FROM payin_transfers
                     WHERE payer = %s
                       AND payin = %s
                """, (payin.payer, payin.id)))
                for sp in schedule:
                    if any((tr['tippee_id'] in payin_tippees) for tr in sp.transfers):
                        cursor.run("""
                            UPDATE scheduled_payins
                               SET payin = %s
                                 , mtime = current_timestamp
                             WHERE id = %s
                        """, (payin.id, sp.id))
                        break

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
    min_transfer_amount = get_minimum_transfer_amount(provider, net_amount.currency)
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
        if any(pt.status == 'succeeded' for pt in payin_transfers):
            # At least one of the transfers has already been executed, so it's
            # too complicated to adjust the amounts now.
            return
        transfers_by_tippee = group_by(
            payin_transfers, lambda pt: (pt.team or pt.recipient)
        )
        prorated_amounts = resolve_amounts(net_amount, {
            tippee: MoneyBasket(pt.amount for pt in grouped).fuzzy_sum(net_amount.currency)
            for tippee, grouped in transfers_by_tippee.items()
        }, minimum_amount=min_transfer_amount)
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
                        prorated_amount, tip, sepa_only=True,
                    )
                except (AccountSuspended, MissingPaymentAccount, NoSelfTipping, RecipientAccountSuspended):
                    team_amounts = resolve_amounts(prorated_amount, {
                        pt.id: pt.amount.convert(prorated_amount.currency)
                        for pt in transfers
                    }, minimum_amount=min_transfer_amount)
                    for pt in transfers:
                        if pt.amount != team_amounts.get(pt.id):
                            updates.append((team_amounts[pt.id], pt.id))
                else:
                    team_donations = {d.recipient.id: d for d in team_donations}
                    for pt in transfers:
                        d = team_donations.pop(pt.recipient, None)
                        if d is None:
                            cursor.run("""
                                DELETE FROM payin_transfer_events
                                 WHERE payin_transfer = %(pt_id)s
                                   AND status <> 'succeeded';
                                DELETE FROM payin_transfers WHERE id = %(pt_id)s;
                            """, dict(pt_id=pt.id))
                        elif pt.amount != d.amount:
                            updates.append((d.amount, pt.id))
                    n_periods = prorated_amount / tip.periodic_amount.convert(prorated_amount.currency)
                    for d in team_donations.values():
                        unit_amount = (d.amount / n_periods).round(allow_zero=False)
                        prepare_payin_transfer(
                            db, payin, d.recipient, d.destination, 'team-donation',
                            d.amount, tip.visibility, unit_amount, tip.period,
                            team=team.id,
                        )
            else:
                pt = transfers[0]
                if pt.amount != prorated_amount:
                    updates.append((prorated_amount, pt.id))
        if updates:
            execute_batch(cursor, """
                UPDATE payin_transfers
                   SET amount = %s
                 WHERE id = %s;
            """, updates)


def resolve_tip(
    db, tip, tippee, provider, payer, payer_country, payment_amount,
    sepa_only=False, excluded_destinations=set(),
):
    """Prepare to fund a tip.

    Args:
        tip (Row): a row from the `tips` table
        tippee (Participant): the intended beneficiary of the donation
        provider (str): the payment processor ('paypal' or 'stripe')
        payer (Participant): the donor
        payer_country (str): the country the money is supposedly coming from
        payment_amount (Money): the amount of money being sent
        sepa_only (bool): only consider destination accounts within SEPA
        excluded_destinations (set): any `payment_accounts.pk` values to exclude

    Returns:
        a list of `ProtoTransfer` objects

    Raises:
        AccountSuspended: if the payer is suspended
        MissingPaymentAccount: if no suitable destination has been found
        NoSelfTipping: if the donor would end up sending money to themself
        RecipientAccountSuspended: if the tippee's account is suspended
        UserDoesntAcceptTips: if the tippee doesn't accept donations

    """
    assert tip.tipper == payer.id
    assert tip.tippee == tippee.id

    if not tippee.accepts_tips:
        raise UserDoesntAcceptTips(tippee.username)
    if tippee.is_suspended:
        raise RecipientAccountSuspended(tippee)
    if payment_amount.currency not in tippee.accepted_currencies_set:
        raise BadDonationCurrency(tippee, payment_amount.currency)

    if tippee.kind == 'group':
        return resolve_team_donation(
            db, tippee, provider, payer, payer_country, payment_amount, tip,
            sepa_only=sepa_only, excluded_destinations=excluded_destinations,
        )
    else:
        destination = resolve_destination(
            db, tippee, provider, payer, payer_country, payment_amount,
            sepa_only=sepa_only, excluded_destinations=excluded_destinations,
        )
        return [ProtoTransfer(
            payment_amount, tippee, destination, 'personal-donation',
            tip.periodic_amount, tip.period, None, tip.visibility,
        )]


def resolve_destination(
    db, tippee, provider, payer, payer_country, payin_amount,
    sepa_only=False, excluded_destinations=(),
):
    """Figure out where to send a payment.

    Args:
        tippee (Participant): the intended beneficiary of the payment
        provider (str): the payment processor ('paypal' or 'stripe')
        payer (Participant): the user who wants to pay
        payer_country (str): the country the money is supposedly coming from
        payin_amount (Money): the payment amount
        sepa_only (bool): only consider destination accounts within SEPA
        excluded_destinations (set): any `payment_accounts.pk` values to exclude

    Returns:
        Record: a row from the `payment_accounts` table

    Raises:
        MissingPaymentAccount: if no suitable destination has been found
        NoSelfTipping: if the payer would end up sending money to themself

    """
    tippee_id = tippee.id
    if tippee_id == payer.id:
        raise NoSelfTipping()
    currency = payin_amount.currency
    excluded_destinations = list(excluded_destinations)
    destination = db.one("""
        SELECT *
          FROM payment_accounts
         WHERE participant = %(tippee_id)s
           AND provider = %(provider)s
           AND is_current
           AND verified
           AND coalesce(charges_enabled, true)
           AND array_position(%(excluded_destinations)s::bigint[], pk) IS NULL
           AND ( country IN %(SEPA)s OR NOT %(sepa_only)s )
      ORDER BY default_currency = %(currency)s DESC
             , country = %(payer_country)s DESC
             , connection_ts
         LIMIT 1
    """, dict(locals(), SEPA=SEPA))
    if destination:
        return destination
    else:
        raise MissingPaymentAccount(tippee)


def resolve_team_donation(
    db, team, provider, payer, payer_country, payment_amount, tip,
    sepa_only=False, excluded_destinations=(),
):
    """Figure out how to distribute a donation to a team's members.

    Args:
        team (Participant): the team the donation is for
        provider (str): the payment processor ('paypal' or 'stripe')
        payer (Participant): the donor
        payer_country (str): the country code the money is supposedly coming from
        payment_amount (Money): the amount of money being sent
        tip (Tip): the donation this payment will fund
        sepa_only (bool): only consider destination accounts within SEPA
        excluded_destinations (set): any `payment_accounts.pk` values to exclude

    Returns:
        a list of `ProtoTransfer` objects

    Raises:
        AccountSuspended: if the payer is suspended
        MissingPaymentAccount: if no suitable destination has been found
        NoSelfTipping: if the payer would end up sending money to themself
        RecipientAccountSuspended: if the team or all of its members are suspended

    """
    if payer.is_suspended:
        raise AccountSuspended(payer)
    if team.is_suspended:
        raise RecipientAccountSuspended(team)
    currency = payment_amount.currency
    takes = team.get_current_takes_for_payment(currency, tip)
    if all(t.is_suspended for t in takes):
        raise RecipientAccountSuspended(takes)
    takes = [t for t in takes if not t.is_suspended]
    if len(takes) == 1 and takes[0].member == payer.id:
        raise NoSelfTipping()
    member_ids = tuple([t.member for t in takes])
    excluded_destinations = list(excluded_destinations)
    payment_accounts = {row.participant: row for row in db.all("""
        SELECT DISTINCT ON (participant) *
          FROM payment_accounts
         WHERE participant IN %(member_ids)s
           AND provider = %(provider)s
           AND is_current
           AND verified
           AND coalesce(charges_enabled, true)
           AND array_position(%(excluded_destinations)s::bigint[], pk) IS NULL
      ORDER BY participant
             , default_currency = %(currency)s DESC
             , country = %(payer_country)s DESC
             , connection_ts
    """, locals())}
    del member_ids
    if not payment_accounts:
        raise MissingPaymentAccount(team)
    takes = [t for t in takes if t.member in payment_accounts and t.member != payer.id]
    if not takes:
        raise NoSelfTipping()
    takes.sort(key=lambda t: (
        -(t.naive_amount / (t.paid_in_advance + payment_amount)),
        t.paid_in_advance,
        t.ctime
    ))
    # Try to distribute the donation to multiple members.
    if sepa_only or provider == 'stripe':
        sepa_accounts = {a.participant: a for a in db.all("""
            SELECT DISTINCT ON (a.participant) a.*
              FROM payment_accounts a
             WHERE a.participant IN %(member_ids)s
               AND a.provider = %(provider)s
               AND a.is_current
               AND a.verified
               AND coalesce(a.charges_enabled, true)
               AND array_position(%(excluded_destinations)s::bigint[], a.pk) IS NULL
               AND a.country IN %(SEPA)s
          ORDER BY a.participant
                 , a.default_currency = %(currency)s DESC
                 , a.country = %(payer_country)s DESC
                 , a.connection_ts
        """, dict(locals(), SEPA=SEPA, member_ids={t.member for t in takes}))}
        if sepa_only or len(sepa_accounts) > 1 and takes[0].member in sepa_accounts:
            selected_takes = [
                t for t in takes if t.member in sepa_accounts and t.nominal_amount != 0
            ]
            if selected_takes:
                min_transfer_amount = get_minimum_transfer_amount(provider, currency)
                resolve_take_amounts(
                    payment_amount, selected_takes,
                    min_transfer_amount=min_transfer_amount,
                )
                selected_takes.sort(key=attrgetter('member'))
                n_periods = payment_amount / tip.periodic_amount.convert(currency)
                return [
                    ProtoTransfer(
                        t.resolved_amount,
                        db.Participant.from_id(t.member),
                        sepa_accounts[t.member],
                        'team-donation',
                        (t.resolved_amount / n_periods).round(allow_zero=False),
                        tip.period,
                        team.id,
                        tip.visibility,
                    )
                    for t in selected_takes if t.resolved_amount != 0
                ]
            elif sepa_only:
                raise MissingPaymentAccount(team)
    # Fall back to sending the entire donation to the member who "needs" it most.
    member = db.Participant.from_id(takes[0].member)
    account = payment_accounts[member.id]
    return [ProtoTransfer(
        payment_amount, member, account, 'team-donation',
        tip.periodic_amount, tip.period, team.id, tip.visibility,
    )]


def resolve_take_amounts(payment_amount, takes, min_transfer_amount=None):
    """Compute team transfer amounts.

    Args:
        payment_amount (Money): the total amount of money to transfer
        takes (list): rows returned by `team.get_current_takes_for_payment(...)`
        min_transfer_amount (Money | None):
            prevent the returned amounts from falling between zero and this value

    This function doesn't return anything, instead it mutates the given takes,
    adding a `resolved_amount` attribute to each one.

    """
    if all(t.naive_amount == 0 for t in takes):
        replacement_amount = Money.MINIMUMS[payment_amount.currency]
    else:
        replacement_amount = None
    max_weeks_of_advance = 0
    for t in takes:
        t.base_amount = replacement_amount or t.naive_amount
        if t.base_amount == 0:
            t.weeks_of_advance = 0
            continue
        t.weeks_of_advance = t.paid_in_advance / t.base_amount
        if t.weeks_of_advance > max_weeks_of_advance:
            max_weeks_of_advance = t.weeks_of_advance
    base_amounts = {t.member: t.base_amount for t in takes}
    convergence_amounts = {
        t.member: (
            t.base_amount * (max_weeks_of_advance - t.weeks_of_advance)
        ).round_up()
        for t in takes
    }
    tr_amounts = resolve_amounts(
        payment_amount, base_amounts, convergence_amounts,
        minimum_amount=min_transfer_amount,
    )
    for t in takes:
        t.resolved_amount = tr_amounts.get(t.member, payment_amount.zero())


def resolve_amounts(
    available_amount, base_amounts, convergence_amounts=None, maximum_amounts=None,
    payday_id=1, minimum_amount=None,
):
    """Compute transfer amounts.

    Args:
        available_amount (Money):
            the payin amount to split into transfer amounts
        base_amounts (Dict[Any, Money]):
            a map of IDs to raw transfer amounts
        convergence_amounts (Dict[Any, Money] | None):
            an optional map of IDs to ideal additional amounts
        maximum_amounts (Dict[Any, Money] | None):
            an optional map of IDs to maximum amounts
        payday_id (int):
            the ID of the current or next payday, used to rotate who receives
            the remainder when there is a tie
        minimum_amount (Money | None):
            prevent the returned amounts from falling between zero and this value

    Returns a copy of `base_amounts` with updated values.
    """
    if available_amount < (minimum_amount or 0):
        raise ValueError("available_amount can't be less than minimum_amount or 0")

    currency = available_amount.currency
    zero = Money.ZEROS[currency]
    inf = Money('inf', currency)
    if maximum_amounts is None:
        maximum_amounts = {}
    if minimum_amount is None:
        minimum_amount = Money.MINIMUMS[currency]
    r = {}
    amount_left = available_amount

    # Attempt to converge
    if convergence_amounts:
        convergence_amounts = {
            k: v for k, v in convergence_amounts.items()
            if v != 0 and maximum_amounts.get(k) != 0
        }
        convergence_sum = Money.sum(convergence_amounts.values(), currency)
        if convergence_sum != 0:
            if amount_left < convergence_sum:
                # We only have enough for partial convergence, the funds will be
                # allocated in proportion to `convergence_amounts`.
                base_amounts = convergence_amounts
            else:
                if maximum_amounts:
                    # Make sure the convergence amounts aren't higher than the maximums
                    for k, amount in convergence_amounts.items():
                        max_amount = maximum_amounts.get(k, inf)
                        if amount >= max_amount:
                            convergence_amounts[k] = max_amount
                            convergence_sum -= (amount - max_amount)
                            base_amounts.pop(k, None)
                if amount_left == convergence_sum:
                    # We have just enough money for convergence, but only if all
                    # the amounts are above the minimum.
                    below_minimum = {}
                    for k, amount in list(convergence_amounts.items()):
                        if amount < minimum_amount:
                            below_minimum[k] = amount
                            convergence_amounts.pop(k)
                            convergence_sum -= amount
                    if below_minimum:
                        # At least one of the convergence amounts is below the
                        # minimum.
                        r = convergence_amounts
                        amount_left -= convergence_sum
                        if amount_left >= minimum_amount:
                            # Multiple convergence amounts are below the minimum,
                            # but their sum is greater or equal to the minimum,
                            # so we can distribute that sum among them.
                            base_amounts = below_minimum
                    else:
                        return convergence_amounts
                else:
                    # We have more than enough money for full convergence, the extra
                    # funds will be allocated in proportion to `base_amounts`.
                    r = convergence_amounts
                    amount_left -= convergence_sum
        del convergence_sum
    del convergence_amounts

    # Drop the amounts which can only resolve to zero
    base_amounts = {
        k: v for k, v in base_amounts.items()
        if v != 0 and maximum_amounts.get(k, inf) >= minimum_amount
    }

    # Compute the prorated amounts
    base_sum = Money.sum(base_amounts.values(), currency)
    while base_sum > 0 and amount_left > 0:
        curtailed = False
        prev_amount_left = amount_left
        base_ratio = amount_left / base_sum
        for key, base_amount in sorted(base_amounts.items()):
            prev_amount = r.get(key, 0)
            amount = min((base_amount * base_ratio).round_down(), amount_left) + prev_amount
            max_amount = maximum_amounts.get(key, inf)
            if amount >= max_amount:
                amount = max_amount
                curtailed = True
                base_amounts.pop(key)
                base_sum -= base_amount
            if amount < minimum_amount and amount > 0:
                amount = zero
                curtailed = True
            if amount != prev_amount:
                r[key] = amount
                amount_left -= (amount - prev_amount)
        if not curtailed or amount_left >= prev_amount_left:
            break

    # Deal with the leftover caused by rounding down or by the minimum amount
    if amount_left > 0 and base_amounts:
        # Try to distribute in a way that doesn't skew the percentages much.
        # If there's a tie, use the payday ID to rotate the winner every week.
        n = len(base_amounts)

        def compute_priority(item):
            key, current_amount = item
            base_amount = base_amounts[key]
            return (
                current_amount / base_amount,
                (next(item_counter) - payday_id) % n
            )

        loop_counter = itertools.count(1)
        while True:
            prev_amount_left = amount_left
            item_counter = itertools.count(1)
            items = [(k, r.get(k, zero)) for k in base_amounts]
            items.sort(key=compute_priority)
            increment = (amount_left / len(items)).round_up()
            for key, amount in items:
                if amount_left < increment:
                    increment = amount_left
                new_amount = amount + increment
                if new_amount < minimum_amount:
                    new_amount = minimum_amount
                max_amount = maximum_amounts.get(key, inf)
                if new_amount >= max_amount:
                    new_amount = max_amount
                if new_amount != amount:
                    if (new_amount - amount) > amount_left:
                        continue
                    r[key] = new_amount
                    amount_left -= (new_amount - amount)
                    if amount_left == 0:
                        break
            if amount_left == 0 or amount_left >= prev_amount_left:
                break
            i = next(loop_counter)
            if i == 100:
                warnings.warn("excessive number of loop iterations")

    # Final check and return
    if base_amounts:
        assert amount_left == 0, '%r != 0' % amount_left
    return r


def prepare_payin_transfer(
    db, payin, recipient, destination, context, amount, visibility,
    unit_amount=None, period=None, team=None,
):
    """Prepare the allocation of funds from a payin.

    Args:
        payin (Record): a row from the `payins` table
        recipient (Participant): the user who will receive the money
        destination (Record): a row from the `payment_accounts` table
        amount (Money): the amount of money that will be received
        visibility (int): a copy of `tip.visibility`
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
                unit_amount, n_units, period, team, visibility,
                status, ctime)
        VALUES (%s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                'pre', clock_timestamp())
     RETURNING *
    """, (payin.id, payin.payer, recipient.id, destination.pk, context, amount,
          unit_amount, n_units, period, team, abs(visibility)))


def update_payin_transfer(
    db, pt_id, remote_id, status, error, *,
    amount=None, fee=None, destination_amount=None, reversed_amount=None,
    reversed_destination_amount=None, update_donor=True,
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
                 , destination_amount = coalesce(%(destination_amount)s, destination_amount)
                 , reversed_destination_amount = coalesce(
                       %(reversed_destination_amount)s,
                       reversed_destination_amount
                   )
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

        if status == 'suspended' and pt.old_status in ('failed', 'succeeded'):
            raise ValueError(f"can't change status from {pt.old_status!r} to {status!r}")

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
        elif pt.old_reversed_amount:
            params['delta'] += pt.old_reversed_amount
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
    notify=None,
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
        notify (bool | None): whether to notify the payer

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
    if notify is None:
        notify = (
            refund.status in ('pending', 'succeeded') and
            refund.status != refund.old_status and
            refund.ctime > (utcnow() - timedelta(hours=24))
        )
    if notify:
        payin = db.one("SELECT pi FROM payins pi WHERE pi.id = %s", (refund.payin,))
        payer = db.Participant.from_id(payin.payer)
        payer.notify(
            'payin_refund_initiated',
            payin_amount=payin.amount,
            payin_ctime=payin.ctime,
            recipient_names=payin.recipient_names,
            refund_amount=refund.amount,
            refund_reason=refund.reason,
            email_unverified_address=True,
        )
    return refund


def record_payin_transfer_reversal(
    db, pt_id, remote_id, amount, destination_amount, payin_refund_id=None, ctime=None
):
    """Record a transfer reversal.

    Args:
        pt_id (int): the ID of the reversed transfer in our database
        remote_id (int): the ID of the reversal in the payment processor's database
        amount (Money): the reversal amount, must be less or equal to the transfer amount
        destination_amount (Money): the amount debited from the transfer recipient's balance
        payin_refund_id (int): the ID of the associated payin refund in our database
        ctime (datetime): when the refund was initiated

    Returns:
        Record: the row inserted in the `payin_transfer_reversals` table

    """
    return db.one("""
        INSERT INTO payin_transfer_reversals
               (payin_transfer, remote_id, amount, destination_amount,
                payin_refund, ctime)
        VALUES (%(pt_id)s, %(remote_id)s, %(amount)s, %(destination_amount)s,
                %(payin_refund_id)s, coalesce(%(ctime)s, current_timestamp))
   ON CONFLICT (payin_transfer, remote_id) DO UPDATE
           SET amount = excluded.amount
             , destination_amount = excluded.destination_amount
             , payin_refund = excluded.payin_refund
     RETURNING *
    """, locals())
