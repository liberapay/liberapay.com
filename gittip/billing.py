"""This module encapsulates billing logic and db access.

There are two pieces of information for each customer related to billing:

    balanced_account_uri    NULL - This customer has never been billed.
                            'deadbeef' - This customer's card has been
                                validated and associated with a Balanced
                                account.
    last_bill_result        NULL - This customer has not been billed yet.
                            '' - This customer is in good standing.
                            <message> - A error message.

"""
import decimal

import balanced
from aspen import json, log
from aspen.utils import typecheck
from gittip import db, get_tips_and_total
from psycopg2 import IntegrityError


def associate(participant_id, balanced_account_uri, card_uri):
    """Given three unicodes, return a dict.

    This function attempts to associate the credit card details referenced by
    card_uri with a Balanced Account. If the attempt succeeds we cancel the
    transaction. If it fails we log the failure. Even for failure we keep the
    payment_method_token, we don't reset it to None/NULL. It's useful for
    loading the previous (bad) credit card info from Balanced in order to
    prepopulate the form.

    """
    typecheck( participant_id, unicode
             , balanced_account_uri, (unicode, None)
             , card_uri, unicode
              )


    # Load or create a Balanced Account.
    # =================================
    email_address = '{}@gittip.com'.format(
        participant_id
    )
    if balanced_account_uri is None:
        # arg - balanced requires an email address
        try:
            customer = balanced.Account.query.filter(
                email_address=email_address).one()
        except balanced.exc.NoResultFound:
            customer = balanced.Account(email_address=email_address).save()
        CUSTOMER = """\
                
                UPDATE participants 
                   SET balanced_account_uri=%s
                 WHERE id=%s
                
        """
        db.execute(CUSTOMER, (customer.uri, participant_id))
        customer.meta['participant_id'] = participant_id
        customer.save()  # HTTP call under here
    else:
        customer = balanced.Account.find(balanced_account_uri)



    # Associate the card with the customer.
    # =====================================
    # Handle errors. Return a unicode, a simple error message. If empty it
    # means there was no error. Yay! Store any error message from the
    # Balanced API as a string in last_bill_result. That may be helpful for
    # debugging at some point.

    customer.card_uri = card_uri
    try:
        customer.save()
    except balanced.exc.HTTPError as err:
        last_bill_result = err.message
        assert(isinstance(last_bill_result, basestring))
        out = err.message
    else:
        out = last_bill_result = ''
        
    STANDING = """\

    UPDATE participants
       SET last_bill_result=%s 
     WHERE id=%s

    """
    db.execute(STANDING, (last_bill_result, participant_id))
    return out


def clear(participant_id, balanced_account_uri):
    typecheck(participant_id, unicode, balanced_account_uri, unicode)

    # accounts in balanced cannot be deleted at the moment. instead we mark all
    # valid cards as invalid which will restrict against anyone being able to
    # issue charges against them in the future.
    customer = balanced.Account.find(balanced_account_uri)
    for card in customer.cards:
        if card.is_valid:
            card.is_valid = False
            card.save()

    CLEAR = """\

        UPDATE participants
           SET balanced_account_uri=NULL
             , last_bill_result=NULL
         WHERE id=%s

    """
    db.execute(CLEAR, (participant_id,))


MINIMUM = decimal.Decimal("0.50") # per Balanced
FEE = ( decimal.Decimal("0.30")   # $0.30
      , decimal.Decimal("1.039")  #  3.9%
       )


def charge(participant_id, balanced_account_uri, amount):
    """Given two unicodes and a Decimal, return a boolean indicating success.

    This is the only place where we actually charge credit cards. Amount should
    be the nominal amount. We compute Gittip's fee in this function and add
    it to amount.

    """
    typecheck( participant_id, unicode
             , balanced_account_uri, (unicode, None)
             , amount, decimal.Decimal
              )

    if balanced_account_uri is None:
        mark_payday_missing_funding()
        return False

    (charge_amount,
     fee,
     error_message) = charge_balanced_account(participant_id,
                                              balanced_account_uri,
                                              amount)

    # XXX If the power goes out at this point then Postgres will be out of sync
    # with Balanced. We'll have to resolve that manually be reviewing the
    # Balanced transaction log and modifying Postgres accordingly.
    #
    # this could be done by generating an ID locally and commiting that to the
    # db and then passing that through in the meta field -
    # https://www.balancedpayments.com/docs/meta
    # Then syncing would be a case of simply:
    # for payment in unresolved_payments:
    #     payment_in_balanced = balanced.Transaction.query.filter(
    #       **{'meta.unique_id': 'value'}).one()
    #     payment.transaction_uri = payment_in_balanced.uri
    #
    with db.get_connection() as conn:
        cur = conn.cursor()

        if error_message:
            last_bill_result = error_message
            amount = decimal.Decimal('0.00')
            mark_payday_failed(cur)
        else:
            last_bill_result = ''
            mark_payday_success(participant_id,
                                  amount,
                                  fee,
                                  charge_amount,
                                  cur)

        # Update the participant's balance.
        # =================================
        # Credit card charges go immediately to balance, not to pending.

        RESULT = """\

        UPDATE participants
           SET last_bill_result=%s
             , balance=(balance + %s)
         WHERE id=%s

        """
        cur.execute(RESULT, (last_bill_result, amount, participant_id))
        conn.commit()

    return not bool(last_bill_result)  # True indicates success


def mark_payday_missing_funding():
    STATS = """\

        UPDATE paydays
        SET ncc_missing = ncc_missing + 1
        WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
        RETURNING id

        """
    assert_one_payday(db.fetchone(STATS))


def mark_payday_failed(cur):

    STATS = """\

        UPDATE paydays
        SET ncc_failing = ncc_failing + 1
        WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
        RETURNING id

            """
    cur.execute(STATS)
    assert_one_payday(cur.fetchone())


def mark_payday_success(participant_id, amount, fee, charge_amount, cur):

    EXCHANGE = """\

            INSERT INTO exchanges
                   (amount, fee, participant_id)
            VALUES (%s, %s, %s)

            """
    cur.execute(EXCHANGE, (amount, fee, participant_id))

    STATS = """\

                UPDATE paydays
                   SET nexchanges = nexchanges + 1
                     , exchange_volume = exchange_volume + %s
                     , exchange_fees_volume = exchange_fees_volume + %s
                 WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
             RETURNING id

            """
    cur.execute(STATS, (charge_amount, fee))
    assert_one_payday(cur.fetchone())


def charge_balanced_account(participant_id,
                            balanced_account_uri,
                            amount_in_dollars):
    # We have a purported balanced_account_uri. Try to use it.
    # ======================================================

    try_charge_amount = (amount_in_dollars + FEE[0]) * FEE[1]
    try_charge_amount = try_charge_amount.quantize(FEE[0],
                                                   rounding=decimal.ROUND_UP
    )
    charge_amount = try_charge_amount
    also_log = ''
    if charge_amount < MINIMUM:
        charge_amount = MINIMUM  # per Balanced
        also_log = ', rounded up to $%s' % charge_amount

    fee = try_charge_amount - amount_in_dollars
    cents = int(charge_amount * 100)

    msg = "Charging %s %d cents ($%s + $%s fee = $%s%s) ... "
    msg %= participant_id, cents, amount_in_dollars, fee, try_charge_amount, \
           also_log

    try:
        customer = balanced.Account.find(balanced_account_uri)
        customer.debit(cents, description=participant_id)
        log(msg + "succeeded.")
    except balanced.exc.HTTPError as err:
        log(msg + "failed: %s" % err.message)
        return charge_amount, fee, err.description
    return charge_amount, fee, None


def transfer(tipper, tippee, amount):
    """Given two unicodes and a Decimal, return a boolean indicating success.

    If the tipper doesn't have enough in their Gittip account then we return
    False. Otherwise we decrement tipper's balance and increment tippee's
    *pending* balance by amount.

    """
    typecheck(tipper, unicode, tippee, unicode, amount, decimal.Decimal)
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Decrement the tipper's balance.
        # ===============================

        DECREMENT = """\

           UPDATE participants
              SET balance=(balance - %s)
            WHERE id=%s
              AND pending IS NOT NULL
        RETURNING balance

        """
        cursor.execute(DECREMENT, (amount, tipper))
        rec = cursor.fetchone()
        assert rec is not None, (tipper, tippee, amount)  # sanity check
        if rec['balance'] < 0:

            # User is out of money. Bail. The transaction will be rolled back 
            # by our context manager.

            return False


        # Increment the tippee's *pending* balance.
        # =========================================
        # The pending balance will clear to the balance proper when Payday is 
        # done.

        INCREMENT = """\

           UPDATE participants
              SET pending=(pending + %s)
            WHERE id=%s
              AND pending IS NOT NULL
        RETURNING pending

        """
        cursor.execute(INCREMENT, (amount, tippee))
        rec = cursor.fetchone()
        assert rec is not None, (tipper, tippee, amount)  # sanity check


        # Record the transfer.
        # ====================

        RECORD = """\

          INSERT INTO transfers
                      (tipper, tippee, amount)
               VALUES (%s, %s, %s)

        """
        cursor.execute(RECORD, (tipper, tippee, amount))


        # Record some stats.
        # ==================

        STATS = """\

            UPDATE paydays 
               SET ntransfers = ntransfers + 1
                 , transfer_volume = transfer_volume + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """
        cursor.execute(STATS, (amount,))
        assert_one_payday(cursor.fetchone())


        # Success.
        # ========
        
        conn.commit()
        return True


def payday():
    """This is the big one.

    Settling the graph of Gittip balances is an abstract event called Payday.

    On Payday, we want to use a participant's Gittip balance to settle their
    tips due (pulling in more money via credit card as needed), but we only
    want to use their balance at the start of Payday. Balance changes should be
    atomic globally per-Payday.

    This function runs every Friday. It is structured such that it can be run 
    again safely if it crashes.
    
    """
    log("Greetings, program! It's PAYDAY!!!!")

    participants, payday_start = initialize_payday()

    # Drop to core.
    # =============
    # We are now locked for Payday. If the power goes out at this point then we
    # will need to start over and reacquire the lock.
    
    payday_loop(payday_start, participants)

    finish_payday()

def initialize_payday():
    # Start Payday.
    # =============
    # We try to start a new Payday. If there is a Payday that hasn't finished
    # yet, then the UNIQUE constraint on ts_end will kick in and notify us
    # of that. In that case we load the existing Payday and work on it some
    # more. We use the start time of the current Payday to synchronize our
    # work.

    try:
        rec = db.fetchone("INSERT INTO paydays DEFAULT VALUES "
                          "RETURNING ts_start")
        log("Starting a new payday.")
    except IntegrityError:  # Collision, we have a Payday already.
        rec = db.fetchone("""
            SELECT ts_start
            FROM paydays
            WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
        """)
        log("Picking up with an existing payday.")
    assert rec is not None  # Must either create or recycle a Payday.
    payday_start = rec['ts_start']
    log("Payday started at %s." % payday_start)

    START_PENDING = """\

        UPDATE participants
           SET pending=0.00
         WHERE pending IS NULL

    """
    db.execute(START_PENDING)
    log("Zeroed out the pending column.")

    PARTICIPANTS = """\
        SELECT id, balance, balanced_account_uri
          FROM participants
         WHERE claimed_time IS NOT NULL
    """
    participants = db.fetchall(PARTICIPANTS)
    log("Fetched participants.")

    return participants, payday_start


def finish_payday():
    # Finish Payday.
    # ==============
    # Transfer pending into balance for all users, setting pending to NULL.
    # Close out the paydays entry as well.

    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""\

            UPDATE participants
               SET balance = (balance + pending)
                 , pending = NULL

        """)
        cursor.execute("""\

            UPDATE paydays
               SET ts_end=now()
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """)
        assert_one_payday(cursor.fetchone())

        conn.commit()
        log("Finished payday.")


def payday_loop(payday_start, participants):
    """Given an iterator, do Payday.
    """
    i = 0 
    log("Processing participants.")
    for i, participant in enumerate(participants, start=1):
        if i % 100 == 0:
            log("Processed %d participants." % i)
        payday_one(payday_start, participant)
    log("Processed %d participants." % i)


def payday_one(payday_start, participant):
    """Given one participant record, pay their day.

    Charge each participants' credit card if needed before transfering money
    between Gittip accounts.
 
    """
    tips, total = get_tips_and_total( participant['id']
                                    , for_payday=payday_start
                                     )
    typecheck(total, decimal.Decimal)
    short = total - participant['balance']
    if short > 0:
        # The participant's Gittip account is short the amount needed to fund
        # all their tips. Let's try pulling in money from their credit card. If
        # their credit card fails we'll forge ahead, in case they have a
        # positive Gittip balance already that can be used to fund at least
        # *some* tips. The charge method will have set last_bill_result to a
        # non-empty string if the card did fail.

        charge(participant['id'], participant['balanced_account_uri'], short)
 
    successful_tips = 0
    for tip in tips:
        result = log_tip(participant, tip, payday_start)
        if result >= 0:
            successful_tips += result
        else:
            break

    # Update stats.
    # =============

    STATS = """\

        UPDATE paydays 
           SET nparticipants = nparticipants + 1
             , ntippers = ntippers + %s
             , ntips = ntips + %s
         WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
     RETURNING id

    """
    assert_one_payday(db.fetchone(STATS,
        (1 if successful_tips > 0 else 0, successful_tips)))


def log_tip(participant, tip, payday_start):
    """
    Returns
         0 if no valid tip available or tip has not been claimed
         1 if tip is valid
        -1 if transfer fails and we cannot continue
    """
    msg = "$%s from %s to %s."
    msg %= (tip['amount'], participant['id'], tip['tippee'])

    if tip['amount'] == 0:

        # The tips table contains a record for every time you click a tip
        # button. So if you click $0.08 then $0.64 then $0.00, that
        # generates three entries. We are looking at the last entry here,
        # and it's zero.

        return 0

    claimed_time = tip['claimed_time']

    if claimed_time is None or claimed_time > payday_start:

        # Gittip is opt-in. We're only going to collect money on a person's
        # behalf if they opted-in by claiming their account before the
        # start of this payday.

        log("SKIPPED: %s" % msg)
        return 0

    if not transfer(participant['id'], tip['tippee'], tip['amount']):

        # The transfer failed due to a lack of funds for the participant.
        # Don't try any further transfers.

        log("FAILURE: %s" % msg)
        return -1

    log("SUCCESS: %s" % msg)
    return 1


def assert_one_payday(payday):
    """Given the result of a payday stats update, make sure it's okay.
    """
    assert payday is not None 
    payday = list(payday)
    assert len(payday) == 1, payday


# Payment Method
# ==============

class DummyPaymentMethod(dict):
    """Define a dict that can be used when Balanced is unavailable.
    """
    def __getitem__(self, name):
        return ''


class Customer(object):
    """This is a dict-like wrapper around a Balanced Account.
    """

    _customer = None  # underlying balanced.Account object

    def __init__(self, balanced_account_uri):
        """Given a Balanced account_uri, load data from Balanced.
        """
        if balanced_account_uri is not None:
            self._customer = balanced.Account.find(balanced_account_uri)

    def _get(self, name):
        """Given a name, return a string.
        """
        out = ""
        if self._customer is not None:
            try:
                # this is an abortion
                # https://github.com/balanced/balanced-python/issues/3
                cards = self._customer.cards
                cards = sorted(cards, key=lambda c: c.created_at)
                cards.reverse()
                card = cards[0]
                out = getattr(card, name, "")
            except IndexError:  # no cards associated
                pass
            if out is None:
                out = ""
        return out

    def __getitem__(self, name):
        """Given a name, return a string.
        """
        if name == 'id':
            out = self._customer.uri if self._customer is not None else None
        elif name == 'last4':
            out = self._get('last_four')
            if out:
                out = "************" + out
        elif name == 'expiry':
            month = self._get('expiration_month')
            year = self._get('expiration_year')

            if month and year:
                out = "%d/%d" % (month, year)
            else:
                out = ""
        else:
            out = self._get(name)
        return out
