"""Functions for moving money between Gratipay and the outside world.
"""
from __future__ import unicode_literals

from decimal import Decimal, ROUND_UP

import balanced

from aspen import log
from aspen.utils import typecheck
from gratipay.exceptions import NegativeBalance, NoBalancedCustomerHref, NotWhitelisted
from gratipay.models import check_db
from gratipay.models.participant import Participant


# https://docs.balancedpayments.com/1.1/api/customers/
CUSTOMER_LINKS = {
    "customers.bank_accounts": "/customers/{customers.id}/bank_accounts",
    "customers.card_holds": "/customers/{customers.id}/card_holds",
    "customers.cards": "/customers/{customers.id}/cards",
    "customers.credits": "/customers/{customers.id}/credits",
    "customers.debits": "/customers/{customers.id}/debits",
    "customers.destination": "/resources/{customers.destination}",
    "customers.disputes": "/customers/{customers.id}/disputes",
    "customers.external_accounts": "/customers/{customers.id}/external_accounts",
    "customers.orders": "/customers/{customers.id}/orders",
    "customers.refunds": "/customers/{customers.id}/refunds",
    "customers.reversals": "/customers/{customers.id}/reversals",
    "customers.source": "/resources/{customers.source}",
    "customers.transactions": "/customers/{customers.id}/transactions"
}


def customer_from_href(href):
    """This functions "manually" builds a minimal Customer instance.
    """
    id = href.rsplit('/', 1)[1]
    d = {'href': href, 'id': id, 'links': {}, 'meta': {}}
    return balanced.Customer(customers=[d], links=CUSTOMER_LINKS)


# Balanced has a $0.50 minimum. We go even higher to avoid onerous
# per-transaction fees. See:
# https://github.com/gratipay/gratipay.com/issues/167

MINIMUM_CHARGE = Decimal("9.41")
MINIMUM_CREDIT = Decimal("10.00")

FEE_CHARGE = ( Decimal("0.30")   # $0.30
             , Decimal("0.029")  #  2.9%
              )
FEE_CREDIT = Decimal("0.00")    # Balanced doesn't actually charge us for this,
                                # because we were in the door early enough.


def upcharge(amount):
    """Given an amount, return a higher amount and the difference.
    """
    typecheck(amount, Decimal)
    charge_amount = (amount + FEE_CHARGE[0]) / (1 - FEE_CHARGE[1])
    charge_amount = charge_amount.quantize(FEE_CHARGE[0], rounding=ROUND_UP)
    return charge_amount, charge_amount - amount

assert upcharge(MINIMUM_CHARGE) == (Decimal('10.00'), Decimal('0.59'))


def skim_credit(amount):
    """Given an amount, return a lower amount and the difference.
    """
    typecheck(amount, Decimal)
    return amount - FEE_CREDIT, FEE_CREDIT


def repr_exception(e):
    if isinstance(e, balanced.exc.HTTPError):
        return '%s %s, %s' % (e.status_code, e.status, e.description)
    else:
        return repr(e)


def ach_credit(db, participant, withhold, minimum_credit=MINIMUM_CREDIT):

    # Compute the amount to credit them.
    # ==================================
    # Leave money in Gratipay to cover their obligations next week (as these
    # currently stand).

    balance = participant.balance
    assert balance is not None, balance # sanity check
    amount = balance - withhold

    # Do some last-minute checks.
    # ===========================

    if amount <= 0:
        return      # Participant not owed anything.

    if amount < minimum_credit:
        also_log = ""
        if withhold > 0:
            also_log = " ($%s balance - $%s in obligations)"
            also_log %= (balance, withhold)
        log("Minimum payout is $%s. %s is only due $%s%s."
           % (minimum_credit, participant.username, amount, also_log))
        return      # Participant owed too little.

    if not participant.is_whitelisted:
        raise NotWhitelisted      # Participant not trusted.

    balanced_customer_href = participant.balanced_customer_href
    if balanced_customer_href is None:
        log("%s has no balanced_customer_href."
            % participant.username)
        raise NoBalancedCustomerHref  # not in Balanced


    # Do final calculations.
    # ======================

    credit_amount, fee = skim_credit(amount)
    cents = credit_amount * 100

    if withhold > 0:
        also_log = "$%s balance - $%s in obligations"
        also_log %= (balance, withhold)
    else:
        also_log = "$%s" % amount
    msg = "Crediting %s %d cents (%s - $%s fee = $%s) on Balanced ... "
    msg %= (participant.username, cents, also_log, fee, credit_amount)


    # Try to dance with Balanced.
    # ===========================

    e_id = record_exchange(db, 'ach', -credit_amount, fee, participant, 'pre')
    meta = dict(exchange_id=e_id, participant_id=participant.id)
    try:
        customer = customer_from_href(balanced_customer_href)
        ba = customer.bank_accounts.one()
        ba.credit(amount=cents, description=participant.username, meta=meta)
        record_exchange_result(db, e_id, 'pending', None, participant)
        log(msg + "succeeded.")
        error = ""
    except Exception as e:
        error = repr_exception(e)
        record_exchange_result(db, e_id, 'failed', error, participant)
        log(msg + "failed: %s" % error)

    return error


def create_card_hold(db, participant, amount):
    """Create a hold on the participant's credit card.

    Amount should be the nominal amount. We'll compute Gratipay's fee below
    this function and add it to amount to end up with charge_amount.

    """
    typecheck(amount, Decimal)

    username = participant.username
    balanced_customer_href = participant.balanced_customer_href

    typecheck( username, unicode
             , balanced_customer_href, (unicode, None)
              )


    # Perform some last-minute checks.
    # ================================

    if balanced_customer_href is None:
        raise NoBalancedCustomerHref      # Participant has no funding source.

    if participant.is_suspicious is not False:
        raise NotWhitelisted      # Participant not trusted.


    # Go to Balanced.
    # ===============

    cents, amount_str, charge_amount, fee = _prep_hit(amount)
    msg = "Holding " + amount_str + " on Balanced for " + username + " ... "

    hold = None
    try:
        card = customer_from_href(balanced_customer_href).cards.one()
        hold = card.hold( amount=cents
                        , description=username
                        , meta=dict(participant_id=participant.id, state='new')
                         )
        log(msg + "succeeded.")
        error = ""
    except Exception as e:
        error = repr_exception(e)
        log(msg + "failed: %s" % error)
        record_exchange(db, 'bill', amount, fee, participant, 'failed', error)

    return hold, error


def capture_card_hold(db, participant, amount, hold):
    """Capture the previously created hold on the participant's credit card.
    """
    typecheck( hold, balanced.CardHold
             , amount, Decimal
              )

    username = participant.username
    assert participant.id == int(hold.meta['participant_id'])

    cents, amount_str, charge_amount, fee = _prep_hit(amount)
    amount = charge_amount - fee  # account for possible rounding
    e_id = record_exchange(db, 'bill', amount, fee, participant, 'pre')

    meta = dict(participant_id=participant.id, exchange_id=e_id)
    try:
        hold.capture(amount=cents, description=username, meta=meta)
        record_exchange_result(db, e_id, 'succeeded', None, participant)
    except Exception as e:
        error = repr_exception(e)
        record_exchange_result(db, e_id, 'failed', error, participant)
        raise

    hold.meta['state'] = 'captured'
    hold.save()

    log("Captured " + amount_str + " on Balanced for " + username)


def cancel_card_hold(hold):
    """Cancel the previously created hold on the participant's credit card.
    """
    hold.is_void = True
    hold.meta['state'] = 'cancelled'
    hold.save()


def _prep_hit(unrounded):
    """Takes an amount in dollars. Returns cents, etc.

    cents       This is passed to the payment processor charge API. This is
                the value that is actually charged to the participant. It's
                an int.
    amount_str  A detailed string representation of the amount.
    upcharged   Decimal dollar equivalent to `cents'.
    fee         Decimal dollar amount of the fee portion of `upcharged'.

    The latter two end up in the db in a couple places via record_exchange.

    """
    also_log = ''
    rounded = unrounded
    if unrounded < MINIMUM_CHARGE:
        rounded = MINIMUM_CHARGE  # per github/#167
        also_log = ' [rounded up from $%s]' % unrounded

    upcharged, fee = upcharge(rounded)
    cents = int(upcharged * 100)

    amount_str = "%d cents ($%s%s + $%s fee = $%s)"
    amount_str %= cents, rounded, also_log, fee, upcharged

    return cents, amount_str, upcharged, fee


def record_exchange(db, kind, amount, fee, participant, status, error=None):
    """Given a Bunch of Stuff, return None.

    Records in the exchanges table have these characteristics:

        amount  It's negative for credits (representing an outflow from
                Gratipay to you) and positive for charges.
                The sign is how we differentiate the two in, e.g., the
                history page.

        fee     The payment processor's fee. It's always positive.

    """

    with db.get_cursor() as cursor:

        exchange_id = cursor.one("""
            INSERT INTO exchanges
                   (amount, fee, participant, status)
            VALUES (%s, %s, %s, %s)
         RETURNING id
        """, (amount, fee, participant.username, status))

        if status == 'failed':
            propagate_exchange(cursor, participant, kind, error, 0)
        elif amount < 0:
            amount -= fee
            propagate_exchange(cursor, participant, kind, '', amount)

    return exchange_id


def record_exchange_result(db, exchange_id, status, error, participant):
    """Updates the status of an exchange.
    """
    with db.get_cursor() as cursor:
        amount, fee, username = cursor.one("""
            UPDATE exchanges
               SET status=%(status)s
                 , note=%(error)s
             WHERE id=%(exchange_id)s
               AND status <> %(status)s
         RETURNING amount, fee, participant
        """, locals())
        assert participant.username == username

        if amount < 0:
            amount -= fee
            amount = amount if status == 'failed' else 0
            propagate_exchange(cursor, participant, 'ach', error, -amount)
        else:
            amount = amount if status == 'succeeded' else 0
            propagate_exchange(cursor, participant, 'bill', error, amount)


def propagate_exchange(cursor, participant, kind, error, amount):
    """Propagates an exchange to the participant's balance.
    """
    column = 'last_%s_result' % kind
    error = None if error == 'NoResultFound()' else (error or '')
    new_balance = cursor.one("""
        UPDATE participants
           SET {0}=%s
             , balance=(balance + %s)
         WHERE id=%s
     RETURNING balance
    """.format(column), (error, amount, participant.id))

    if amount < 0 and new_balance < 0:
        raise NegativeBalance

    if hasattr(participant, 'set_attributes'):
        participant.set_attributes(**{'balance': new_balance, column: error})


def sync_with_balanced(db):
    """We can get out of sync with Balanced if record_exchange_result was
    interrupted or wasn't called. This is where we fix that.
    """
    check_db(db)
    exchanges = db.all("""
        SELECT *
          FROM exchanges
         WHERE status = 'pre'
    """)
    meta_exchange_id = balanced.Transaction.f.meta.exchange_id
    for e in exchanges:
        p = Participant.from_username(e.participant)
        cls = balanced.Debit if e.amount > 0 else balanced.Credit
        transactions = cls.query.filter(meta_exchange_id == e.id).all()
        assert len(transactions) < 2
        if transactions:
            t = transactions[0]
            error = t.failure_reason
            status = t.status
            assert (not error) ^ (status == 'failed')
            record_exchange_result(db, e.id, status, error, p)
        else:
            # The exchange didn't happen, remove it
            db.run("DELETE FROM exchanges WHERE id=%s", (e.id,))
            # and restore the participant's balance if it was a credit
            if e.amount < 0:
                db.run("""
                    UPDATE participants
                       SET balance=(balance + %s)
                     WHERE id=%s
                """, (-e.amount + e.fee, p.id))
    check_db(db)
