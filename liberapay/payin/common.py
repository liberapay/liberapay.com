from ..exceptions import (
    AccountSuspended, MissingPaymentAccount, RecipientAccountSuspended,
    NoSelfTipping,
)
from ..i18n.currencies import Money
from ..models.participant import Participant


def prepare_payin(db, payer, amount, route):
    """Prepare to charge a user.

    Args:
        payer (Participant): the user who will be charged
        amount (Money): the presentment amount of the charge
        route (ExchangeRoute): the payment instrument to charge

    Returns:
        Record: the row created in the `payins` table

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


def update_payin(db, payin_id, remote_id, status, error, amount_settled=None, fee=None):
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
                 , remote_id = %(remote_id)s
                 , amount_settled = COALESCE(%(amount_settled)s, amount_settled)
                 , fee = COALESCE(%(fee)s, fee)
             WHERE id = %(payin_id)s
               AND status <> %(status)s
         RETURNING *
        """, locals())
        if not payin:
            return cursor.one("SELECT * FROM payins WHERE id = %s", (payin_id,))

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


def resolve_destination(db, tippee, provider, payer, payer_country, payin_amount):
    """Figure out where to send a payment.

    Args:
        tippee (Participant): the intended beneficiary of the payment (can be a team)
        provider (str): the payment processor ('paypal' or 'stripe')
        payer (Participant): the user who wants to pay
        payer_country (str): the country code the money is supposedly coming from
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
    if tippee.kind != 'group':
        raise MissingPaymentAccount(tippee)
    members = db.all("""
        SELECT t.member
             , t.ctime
             , (coalesce_currency_amount((
                   SELECT sum(pt.amount, 'EUR')
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
             , (convert(t.amount, 'EUR') + coalesce_currency_amount((
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
               ), 'EUR')) AS takes_sum_eur
          FROM current_takes t
         WHERE t.team = %s
           AND t.amount <> 0
           AND EXISTS (
                   SELECT true
                     FROM payment_accounts a
                    WHERE a.participant = t.member
                      AND a.provider = %s
                      AND a.is_current
                      AND a.verified
                      AND coalesce(a.charges_enabled, true)
               )
    """, (tippee.id, provider))
    if not members:
        raise MissingPaymentAccount(tippee)
    payin_amount_eur = payin_amount.convert('EUR')
    zero_eur = Money.ZEROS['EUR']
    members = sorted(members, key=lambda t: (
        int(t.member == payer.id),
        -max(t.takes_sum_eur, zero_eur) / (t.received_sum_eur + payin_amount_eur),
        t.received_sum_eur,
        t.ctime
    ))
    member = Participant.from_id(members[0].member)
    return resolve_destination(db, member, provider, payer, payer_country, payin_amount)


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
    amount=None, fee=None, update_donor=True
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
                 , remote_id = %(remote_id)s
                 , amount = COALESCE(%(amount)s, amount)
                 , fee = COALESCE(%(fee)s, fee)
             WHERE id = %(pt_id)s
               AND status <> %(status)s
         RETURNING *
        """, locals())
        if not pt:
            return cursor.one("SELECT * FROM payin_transfers WHERE id = %s", (pt_id,))

        cursor.run("""
            INSERT INTO payin_transfer_events
                   (payin_transfer, status, error, timestamp)
            VALUES (%s, %s, %s, current_timestamp)
        """, (pt_id, status, error))

        # If the payment has failed or hasn't been settled yet, then stop here.
        if status != 'succeeded':
            return pt

        # Increase the `paid_in_advance` value of the donation.
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
                       convert(%(amount)s, amount::currency)
                   )
                 , is_funded = true
             WHERE id = (SELECT id FROM current_tip)
         RETURNING paid_in_advance
        """, pt._asdict())
        assert paid_in_advance > 0, locals()

        # If it's a team donation, increase the `paid_in_advance` value of the take.
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
                           convert(%(amount)s, amount::currency)
                       )
                 WHERE id = (SELECT id FROM current_take)
             RETURNING paid_in_advance
            """, pt._asdict())
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
