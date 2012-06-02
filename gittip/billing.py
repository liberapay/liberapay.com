"""This module encapsulates billing logic and db access.

There are two pieces of information for each customer related to billing:

    payment_method_token    NULL - This customer has never been billed, even 
                                unsuccessfully.
                            'deadbeef' - This customer has been billed at least
                                once, possibly unsuccessfully. Samurai gives us
                                a so-called "pmt" no matter what garbage credit
                                card info we send to them. We keep it around so
                                that we can prepopulate the customer's payment 
                                details form even if it was unsuccessful last 
                                time around. We don't find out whether the pmt
                                is good until we actually try to charge against
                                it.

    last_bill_result        NULL - This customer has not been billed yet.
                            '' - This customer is in good standing.
                            <json> - A struct of errors encoded as JSON.

"""
import decimal

from aspen import json, log
from aspen.utils import typecheck
from gittip import db, get_tips_and_total
from psycopg2 import IntegrityError
from samurai.payment_method import PaymentMethod as SamuraiPaymentMethod
from samurai.processor import Processor


def redact_pmt(pmt):
    """Given a unicode, redact it with Samurai.
    """
    typecheck(pmt, (unicode, None))
    if pmt is not None:
        pm = PaymentMethod(pmt)
        if pm['payment_method_token']:
            pm._payment_method.redact()


def authorize(participant_id, pmt):
    """Given two unicodes, return a dict.

    This function attempts to authorize the credit card details referenced by
    pmt. If the attempt succeeds we cancel the transaction. If it fails we log
    the failure. Even for failure we keep the payment_method_token, we don't
    reset it to None/NULL. It's useful for loading the previous (bad) credit
    card info from Samurai in order to prepopulate the form.

    """
    typecheck(pmt, unicode, participant_id, unicode)
    transaction = Processor.authorize(pmt, '1.00', custom=participant_id)
    if transaction.errors:
        last_bill_result = json.dumps(transaction.errors)
        out = dict(transaction.errors)
    else:
        transaction.reverse()
        last_bill_result = ''
        out = {}
        
    STANDING = """\

    UPDATE participants
       SET payment_method_token=%s
         , last_bill_result=%s 
     WHERE id=%s

    """
    db.execute(STANDING, (pmt, last_bill_result, participant_id))
    return out


def clear(participant_id, pmt):
    redact_pmt(pmt)
    CLEAR = """\

        UPDATE participants
           SET payment_method_token=NULL
             , last_bill_result=NULL
         WHERE id=%s

    """
    db.execute(CLEAR, (participant_id,))


FEE = ( decimal.Decimal("0.10")   # $0.10
      , decimal.Decimal("1.039")  #  3.9%
       )

def charge(participant_id, pmt, amount):
    """Given two unicodes and a Decimal, return a boolean indicating success.

    This is the only place where we actually charge credit cards. Amount should
    be the nominal amount. We compute Gittip's fee in this function and add
    it to amount.

    """
    typecheck( pmt, (unicode, None)
             , participant_id, unicode
             , amount, decimal.Decimal
              )

    if pmt is None:
        STATS = """\

            UPDATE paydays 
               SET npmt_missing = npmt_missing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id
        
        """
        assert_one_payday(db.fetchone(STATS))
        return False 


    # We have a purported payment method token. Try to use it.
    # ========================================================

    charge_amount = (amount + FEE[0]) * FEE[1]
    charge_amount = charge_amount.quantize(FEE[0], rounding=decimal.ROUND_UP)
    fee = charge_amount - amount
    log("Charging %s $%s + $%s fee = $%s." 
       % (participant_id, amount, fee, charge_amount))
    transaction = Processor.purchase(pmt, charge_amount, custom=participant_id)

    # XXX If the power goes out at this point then Postgres will be out of sync
    # with Samurai. We'll have to resolve that manually be reviewing the
    # Samurai transaction log and modifying Postgres accordingly.

    with db.get_connection() as conn:
        cur = conn.cursor()

        if transaction.errors:
            last_bill_result = json.dumps(transaction.errors)
            amount = decimal.Decimal('0.00')

            STATS = """\

                UPDATE paydays 
                   SET npmt_failing = npmt_failing + 1
                 WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
             RETURNING id
            
            """
            cur.execute(STATS)
            assert_one_payday(cur.fetchone())

        else:
            last_bill_result = ''

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
        rec = db.fetchone("SELECT ts_start FROM paydays WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz")
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
        SELECT id, balance, payment_method_token AS pmt
          FROM participants
    """
    participants = db.fetchall(PARTICIPANTS)
    log("Fetched participants.")
  

    # Drop to core.
    # =============
    # We are now locked for Payday. If the power goes out at this point then we
    # will need to start over and reacquire the lock.
    
    payday_loop(payday_start, participants)


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
        charge(participant['id'], participant['pmt'], short)
 
    ntips = 0 
    for tip in tips:
        if tip['amount'] == 0:
            continue
        if not transfer(participant['id'], tip['tippee'], tip['amount']):
            # The transfer failed due to a lack of funds for the 
            # participant. Don't try any further transfers.
            log("FAILURE: $%s from %s to %s." % (tip['amount'], participant['id'], tip['tippee']))
            break
        log("SUCCESS: $%s from %s to %s." % (tip['amount'], participant['id'], tip['tippee']))
        ntips += 1


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
    assert_one_payday(db.fetchone(STATS, (1 if ntips > 0 else 0, ntips)))


def assert_one_payday(payday):
    """Given the result of a payday stats update, clear it.
    """
    assert payday is not None 
    payday = list(payday)
    assert len(payday) == 1, payday


# Payment Method
# ==============

class DummyPaymentMethod(dict):
    """Define a dict that can be used when Samurai is unavailable.
    """
    def __getitem__(self, name):
        return ''

class PaymentMethod(object):
    """This is a dict-like wrapper around a Samurai PaymentMethod.
    """

    _payment_method = None # underlying payment method

    def __init__(self, pmt):
        """Given a payment method token, loads data from Samurai.
        """
        if pmt is not None:
           self._payment_method = SamuraiPaymentMethod.find(pmt)

    def _get(self, name):
        """Given a name, return a string.
        """
        out = ""
        if self._payment_method is not None:
            out = getattr(self._payment_method, name, "")
            if out is None:
                out = ""
        return out

    def __getitem__(self, name):
        """Given a name, return a string.
        """
        if name == 'last_four':
            out = self._get('last_four_digits')
            if out:
                out = "************" + out
        elif name == 'expiry':
            month = self._get('expiry_month')
            year = self._get('expiry_year')

            # work around https://github.com/FeeFighters/samurai-client-python/issues/7
            if isinstance(month, dict): month = ''
            if isinstance(year, dict):  year = ''

            if month and year:
                out = "%d/%d" % (month, year)
            else:
                out = ""
        else:
            out = self._get(name)
        return out
