from __future__ import unicode_literals

from decimal import Decimal, ROUND_UP

import balanced
import stripe
from aspen import log
from aspen.utils import typecheck
from gittip import get_tips_and_total
from psycopg2 import IntegrityError


MINIMUM = Decimal("10.00")  # Balanced has a $0.50 minimum. We go even higher 
                            # to avoid onerous per-transaction fees. See:
                            # https://github.com/whit537/www.gittip.com/issues/166
FEE = ( Decimal("0.30")   # $0.30
      , Decimal("1.039")  #  3.9%
       )


class Payday(object):
    """Represent an abstract event during which money is moved.

    On Payday, we want to use a participant's Gittip balance to settle their
    tips due (pulling in more money via credit card as needed), but we only
    want to use their balance at the start of Payday. Balance changes should be
    atomic globally per-Payday.

    """

    def __init__(self, db):
        """Takes a gittip.postgres.PostgresManager instance.
        """
        self.db = db


    def run(self):
        """This is the starting point for payday.

        This method runs every Friday. It is structured such that it can be run
        again safely (with a newly-instantiated Payday object) if it crashes.

        """
        log("Greetings, program! It's PAYDAY!!!!")
        ts_start = self.start()
        self.zero_out_pending()
        participants = self.get_participants()
        self.loop(ts_start, participants)
        self.end()


    def start(self):
        """Try to start a new Payday.
        
        If there is a Payday that hasn't finished yet, then the UNIQUE
        constraint on ts_end will kick in and notify us of that. In that case
        we load the existing Payday and work on it some more. We use the start
        time of the current Payday to synchronize our work.

        """
        try:
            rec = self.db.fetchone("INSERT INTO paydays DEFAULT VALUES "
                                   "RETURNING ts_start")
            log("Starting a new payday.")
        except IntegrityError:  # Collision, we have a Payday already.
            rec = self.db.fetchone("""

                SELECT ts_start
                  FROM paydays
                 WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz

            """)
            log("Picking up with an existing payday.")
        assert rec is not None  # Must either create or recycle a Payday.

        ts_start = rec['ts_start']
        log("Payday started at %s." % ts_start)
        return ts_start


    def zero_out_pending(self):
        """Zero out the pending column.

        We keep track of balance changes as a result of Payday in the pending
        column, and then move them over to the balance column in one big
        transaction at the end of Payday.

        """
        START_PENDING = """\

            UPDATE participants
               SET pending=0.00
             WHERE pending IS NULL

        """
        self.db.execute(START_PENDING)
        log("Zeroed out the pending column.")
        return None


    def get_participants(self):
        """Return an iterator of participants dicts.
        """
        PARTICIPANTS = """\
            SELECT id, balance, balanced_account_uri, stripe_customer_id
              FROM participants
             WHERE claimed_time IS NOT NULL
        """
        participants = self.db.fetchall(PARTICIPANTS)
        log("Fetched participants.")
        return participants


    def loop(self, ts_start, participants):
        """Given an iterator, do Payday.
        """
        i = 0 
        log("Processing participants.")
        for i, participant in enumerate(participants, start=1):
            if i % 100 == 0:
                log("Processed %d participants." % i)
            self.charge_and_or_transfer(ts_start, participant)
        log("Processed %d participants." % i)


    def charge_and_or_transfer(self, ts_start, participant):
        """Given one participant record, pay their day.

        Charge each participants' credit card if needed before transfering
        money between Gittip accounts.
     
        """
        tips, total = get_tips_and_total( participant['id']
                                        , for_payday=ts_start
                                        , db=self.db
                                         )
        typecheck(total, Decimal)
        short = total - participant['balance']
        if short > 0:

            # The participant's Gittip account is short the amount needed to
            # fund all their tips. Let's try pulling in money from their credit
            # card. If their credit card fails we'll forge ahead, in case they
            # have a positive Gittip balance already that can be used to fund
            # at least *some* tips. The charge method will have set
            # last_bill_result to a non-empty string if the card did fail.

            self.charge( participant['id']
                       , participant['balanced_account_uri']
                       , participant['stripe_customer_id']
                       , short
                        )
     
        nsuccessful_tips = 0
        for tip in tips:
            result = self.tip(participant, tip, ts_start)
            if result >= 0:
                nsuccessful_tips += result
            else:
                break

        self.mark_participant(nsuccessful_tips)


    def end(self):
        """End Payday.

        Transfer pending into balance for all users, setting pending to NULL.
        Close out the paydays entry as well.

        """

        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""\

                UPDATE participants
                   SET balance = (balance + pending)
                     , pending = NULL

            """)
            self.mark_end(cursor)

            conn.commit()
            log("Finished payday.")


    # Move money between Gittip participants.
    # =======================================

    def tip(self, participant, tip, ts_start):
        """Given dict, dict, and datetime, log and return int.

        Return values:

             0 if no valid tip available or tip has not been claimed
             1 if tip is valid
            -1 if transfer fails and we cannot continue

        """
        msg = "$%s from %s to %s."
        msg %= (tip['amount'], participant['id'], tip['tippee'])

        if tip['amount'] == 0:

            # The tips table contains a record for every time you click a tip
            # button. So if you click $0.25 then $3.00 then $0.00, that
            # generates three entries. We are looking at the last entry here,
            # and it's zero.

            return 0

        claimed_time = tip['claimed_time']
        if claimed_time is None or claimed_time > ts_start:

            # Gittip is opt-in. We're only going to collect money on a person's
            # behalf if they opted-in by claiming their account before the
            # start of this payday.

            log("SKIPPED: %s" % msg)
            return 0

        if not self.transfer(participant['id'], tip['tippee'], tip['amount']):

            # The transfer failed due to a lack of funds for the participant.
            # Don't try any further transfers.

            log("FAILURE: %s" % msg)
            return -1

        log("SUCCESS: %s" % msg)
        return 1


    def transfer(self, tipper, tippee, amount):
        """Given two unicodes and a Decimal, return a boolean.

        If the tipper doesn't have enough in their Gittip account then we
        return False. Otherwise we decrement tipper's balance and increment
        tippee's *pending* balance by amount.

        """
        typecheck(tipper, unicode, tippee, unicode, amount, Decimal)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            try:
                self.debit_participant(cursor, tipper, amount)
            except ValueError:
                return False

            self.credit_participant(cursor, tippee, amount)
            self.record_transfer(cursor, tipper, tippee, amount)
            self.mark_transfer(cursor, amount)

            conn.commit()
            return True


    def debit_participant(self, cursor, participant, amount):
        """Decrement the tipper's balance.
        """

        DECREMENT = """\

           UPDATE participants
              SET balance=(balance - %s)
            WHERE id=%s
              AND pending IS NOT NULL
        RETURNING balance

        """
        cursor.execute(DECREMENT, (amount, participant))
        rec = cursor.fetchone()
        assert rec is not None, (amount, participant)  # sanity check
        if rec['balance'] < 0:
            # User is out of money. Bail. The transaction will be rolled back
            # by our context manager.
            raise ValueError()  # TODO: proper exception type


    def credit_participant(self, cursor, participant, amount):
        """Increment the tippee's *pending* balance.
        
        The pending balance will clear to the balance proper when Payday is
        done.

        """

        INCREMENT = """\

           UPDATE participants
              SET pending=(pending + %s)
            WHERE id=%s
              AND pending IS NOT NULL
        RETURNING pending

        """
        cursor.execute(INCREMENT, (amount, participant))
        rec = cursor.fetchone()
        assert rec is not None, (participant, amount)  # sanity check


    def record_transfer(self, cursor, tipper, tippee, amount):
        RECORD = """\

          INSERT INTO transfers
                      (tipper, tippee, amount)
               VALUES (%s, %s, %s)

        """
        cursor.execute(RECORD, (tipper, tippee, amount))


    # Move money into Gittip from the outside world.
    # ==============================================

    def charge(self, participant_id, balanced_account_uri, stripe_customer_id, amount):
        """Given three unicodes and a Decimal, return a boolean.

        This is the only place where we actually charge credit cards. Amount
        should be the nominal amount. We compute Gittip's fee in this function
        and add it to amount.

        """
        typecheck( participant_id, unicode
                 , balanced_account_uri, (unicode, None)
                 , amount, Decimal
                  )

        if balanced_account_uri is None and stripe_customer_id is None:
            self.mark_missing_funding()
            return False

        if balanced_account_uri is not None:
            charge_amount, fee, error = self.hit_balanced( participant_id
                                                         , balanced_account_uri
                                                         , amount
                                                          )
        else:
            assert stripe_customer_id is not None
            charge_amount, fee, error = self.hit_stripe( participant_id
                                                       , stripe_customer_id
                                                       , amount
                                                        )

        # XXX If the power goes out at this point then Postgres will be out of
        # sync with Balanced. We'll have to resolve that manually be reviewing
        # the Balanced transaction log and modifying Postgres accordingly.
        # 
        # this could be done by generating an ID locally and commiting that to 
        # the db and then passing that through in the meta field -
        # https://www.balancedpayments.com/docs/meta
        # Then syncing would be a case of simply:
        # for payment in unresolved_payments:
        #     payment_in_balanced = balanced.Transaction.query.filter(
        #       **{'meta.unique_id': 'value'}).one()
        #     payment.transaction_uri = payment_in_balanced.uri
        
        with self.db.get_connection() as connection:
            cursor = connection.cursor()

            if error:
                last_bill_result = error
                amount = Decimal('0.00')
                self.mark_failed(cursor)
            else:
                last_bill_result = ''
                EXCHANGE = """\

                        INSERT INTO exchanges
                               (amount, fee, participant_id)
                        VALUES (%s, %s, %s)

                """
                cursor.execute(EXCHANGE, (amount, fee, participant_id))
                self.mark_success(cursor, charge_amount, fee)


            # Update the participant's balance.
            # =================================
            # Credit card charges go immediately to balance, not to pending.

            RESULT = """\

            UPDATE participants
               SET last_bill_result=%s
                 , balance=(balance + %s)
             WHERE id=%s

            """
            cursor.execute(RESULT, (last_bill_result, amount, participant_id))


            connection.commit()

        return not bool(last_bill_result)  # True indicates success


    def hit_balanced(self, participant_id, balanced_account_uri, amount):
        """We have a purported balanced_account_uri. Try to use it.
        """
        typecheck( participant_id, unicode
                 , balanced_account_uri, unicode
                 , amount, Decimal
                  )

        cents, msg, charge_amount, fee = self._prep_hit(amount)
        msg = msg % (participant_id, "Balanced")

        try:
            customer = balanced.Account.find(balanced_account_uri)
            customer.debit(cents, description=participant_id)
            log(msg + "succeeded.")
            error = ""
        except balanced.exc.HTTPError as err:
            error = err.message
            log(msg + "failed: %s" % error)

        return charge_amount, fee, error


    def hit_stripe(self, participant_id, stripe_customer_id, amount):
        """We have a purported stripe_customer_id. Try to use it.
        """
        typecheck( participant_id, unicode
                 , stripe_customer_id, unicode
                 , amount, Decimal
                  )

        cents, msg, charge_amount, fee = self._prep_hit(amount)
        msg = msg % (participant_id, "Stripe")

        try:
            stripe.Charge.create( customer=stripe_customer_id
                                , amount=cents
                                , description=participant_id
                                , currency="USD"
                                 )
            log(msg + "succeeded.")
            error = ""
        except stripe.StripeError, err:
            error = err.message
            log(msg + "failed: %s" % error)

        return charge_amount, fee, error


    def _prep_hit(self, amount):
        """Takes the nominal amount in dollars. Returns cents.
        """
        try_charge_amount = (amount + FEE[0]) * FEE[1]
        try_charge_amount = try_charge_amount.quantize( FEE[0]
                                                      , rounding=ROUND_UP
                                                       )
        charge_amount = try_charge_amount
        also_log = ''
        if charge_amount < MINIMUM:
            charge_amount = MINIMUM  # per Balanced
            also_log = ', rounded up to $%s' % charge_amount

        fee = try_charge_amount - amount
        cents = int(charge_amount * 100)

        msg = "Charging %%s %d cents ($%s + $%s fee = $%s%s) on %%s ... "
        msg %= cents, amount, fee, try_charge_amount, also_log

        return cents, msg, charge_amount, fee


    # Record-keeping.
    # ===============

    def mark_missing_funding(self):
        STATS = """\

            UPDATE paydays
               SET ncc_missing = ncc_missing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """
        self.assert_one_payday(self.db.fetchone(STATS))


    def mark_failed(self, cursor):
        STATS = """\

            UPDATE paydays
               SET ncc_failing = ncc_failing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """
        cursor.execute(STATS)
        self.assert_one_payday(cursor.fetchone())


    def mark_success(self, cursor, charge_amount, fee):
        STATS = """\

            UPDATE paydays
               SET nexchanges = nexchanges + 1
                 , exchange_volume = exchange_volume + %s
                 , exchange_fees_volume = exchange_fees_volume + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """
        cursor.execute(STATS, (charge_amount, fee))
        self.assert_one_payday(cursor.fetchone())


    def mark_transfer(self, cursor, amount):
        STATS = """\

            UPDATE paydays
               SET ntransfers = ntransfers + 1
                 , transfer_volume = transfer_volume + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """
        cursor.execute(STATS, (amount,))
        self.assert_one_payday(cursor.fetchone())


    def mark_participant(self, nsuccessful_tips):
        STATS = """\

            UPDATE paydays 
               SET nparticipants = nparticipants + 1
                 , ntippers = ntippers + %s
                 , ntips = ntips + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """
        self.assert_one_payday( self.db.fetchone( STATS
                                           , ( 1 if nsuccessful_tips > 0 else 0
                                             , nsuccessful_tips  # XXX bug?
                                              )
                                            )
                               )


    def mark_end(self, cursor):
        cursor.execute("""\

            UPDATE paydays
               SET ts_end=now()
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """)
        self.assert_one_payday(cursor.fetchone())


    def assert_one_payday(self, payday):
        """Given the result of a payday stats update, make sure it's okay.
        """
        assert payday is not None 
        payday = list(payday)
        assert len(payday) == 1, payday
