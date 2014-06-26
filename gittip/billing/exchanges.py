"""Functions for moving money between Gittip and the outside world.
"""
from __future__ import unicode_literals

from decimal import Decimal, ROUND_UP
import sys

import balanced

from aspen import log
from aspen.utils import typecheck
from gittip.exceptions import NegativeBalance, NoBalancedCustomerHref, NotWhitelisted


# Balanced has a $0.50 minimum. We go even higher to avoid onerous
# per-transaction fees. See:
# https://github.com/gittip/www.gittip.com/issues/167

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


def ach_credit(db, participant, withhold, minimum_credit=MINIMUM_CREDIT):

    # Compute the amount to credit them.
    # ==================================
    # Leave money in Gittip to cover their obligations next week (as these
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

    try:
        customer = balanced.Customer.fetch(balanced_customer_href)
        customer.bank_accounts.one()\
                              .credit(amount=cents,
                                      description=participant.username)

        log(msg + "succeeded.")
        error = ""
    except balanced.exc.HTTPError as err:
        error = err.message.message
    except:
        error = repr(sys.exc_info()[1])

    if error:
        log(msg + "failed: %s" % error)

    record_exchange(db, 'ach', -credit_amount, fee, error, participant)
    return error


def create_card_hold(db, participant, amount):
    """Create a hold on the participant's credit card.

    Amount should be the nominal amount. We'll compute Gittip's fee below
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
        card = balanced.Customer.fetch(balanced_customer_href).cards.one()
        hold = card.hold( amount=cents
                        , description=username
                        , meta=dict(participant_id=participant.id, state='new')
                         )
        log(msg + "succeeded.")
        error = ""
    except balanced.exc.HTTPError as err:
        error = err.message.message
    except:
        error = repr(sys.exc_info()[1])

    if error:
        log(msg + "failed: %s" % error)
        record_exchange(db, 'bill', None, None, error, participant)

    return hold, error


def capture_card_hold(db, participant, amount, hold):
    """Capture the previously created hold on the participant's credit card.
    """
    typecheck( hold, balanced.CardHold
             , amount, Decimal
              )

    username = participant.username

    cents, amount_str, charge_amount, fee = _prep_hit(amount)

    hold.capture(amount=cents, description=username)
    hold.meta['state'] = 'captured'
    hold.save()

    log("Captured " + amount_str + " on Balanced for " + username)

    amount = charge_amount - fee  # account for possible rounding
    record_exchange(db, 'bill', amount, fee, '', participant)


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


def record_exchange(db, kind, amount, fee, error, participant):
    """Given a Bunch of Stuff, return None.

    Records in the exchanges table have these characteristics:

        amount  It's negative for credits (representing an outflow from
                Gittip to you) and positive for charges.
                The sign is how we differentiate the two in, e.g., the
                history page.

        fee     The payment processor's fee. It's always positive.

    This function takes the result of an API call to a payment processor
    and records the result in our db. If the power goes out at this point
    then Postgres will be out of sync with the payment processor. We'll
    have to resolve that manually be reviewing the transaction log at the
    processor and modifying Postgres accordingly.

    For Balanced, this could be automated by generating an ID locally and
    commiting that to the db and then passing that through in the meta
    field.* Then syncing would be a case of simply::

        for payment in unresolved_payments:
            payment_in_balanced = balanced.Transaction.query.filter(
              **{'meta.unique_id': 'value'}).one()
            payment.transaction_uri = payment_in_balanced.uri

    * https://www.balancedpayments.com/docs/meta

    """

    username = participant.username
    with db.get_cursor() as cursor:

        if error:
            amount = fee = Decimal('0.00')
        else:
            EXCHANGE = """\

                    INSERT INTO exchanges
                           (amount, fee, participant)
                    VALUES (%s, %s, %s)

            """
            cursor.execute(EXCHANGE, (amount, fee, username))

        # Update the participant's balance.
        # =================================

        RESULT = """\

            UPDATE participants
               SET last_{0}_result=%s
                 , balance=(balance + %s)
             WHERE username=%s
         RETURNING balance

        """.format(kind)
        if kind == 'ach':
            amount -= fee
        balance = cursor.one(RESULT, (error or '', amount, username))
        if balance < 0:
            raise NegativeBalance

    if hasattr(participant, 'set_attributes'):
        attrs = dict(balance=balance)
        attrs['last_%s_result' % kind] = error or ''
        participant.set_attributes(**attrs)
