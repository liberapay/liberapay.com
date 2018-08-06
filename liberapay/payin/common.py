from __future__ import division, print_function, unicode_literals

from ..exceptions import AccountSuspended
from ..models.participant import Participant
from ..utils.currencies import Money


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

        _propagate_payin_update(cursor, payin)

        return payin


def _propagate_payin_update(cursor, payin):
    status = payin.status
    if status == 'pre':
        return
    # Update the statuses of the payin's transfers.
    payin_transfers = cursor.all("""
        UPDATE payin_transfers
           SET status = %s
         WHERE payin = %s
     RETURNING *
    """, (payin.status, payin.id))
    # If the payment has failed or hasn't been settled yet, then stop here.
    if status != 'succeeded':
        return
    # Increase the `paid_in_advance` values of donations, and recompute the
    # cached `receiving` amount of each donee.
    for pt in payin_transfers:
        r = cursor.one("""
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
        assert r, locals()
        cursor.run("""
            UPDATE participants AS p
               SET receiving = taking + coalesce_currency_amount((
                       SELECT sum(t.amount, p.main_currency)
                         FROM current_tips t
                        WHERE t.tippee = p.id
                          AND t.amount > 0
                          AND t.is_funded
                   ), p.main_currency)
             WHERE p.id = %s
        """, (pt.team or pt.recipient,))
    # Recompute the cached `giving` amount of the donor.
    Participant.from_id(pt.payer).update_giving(cursor)


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
