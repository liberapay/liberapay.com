"""This is Gittip's payday algorithm. I would appreciate feedback on it.

The payday algorithm is designed to be crash-resistant and parallelizable, but
it's not eventually consistent in the strict sense (iinm) because consistency
is always apodeictically knowable.

Exchanges (moving money between Gittip and the outside world) and transfers
(moving money amongst Gittip users) happen within an isolated event called
payday. This event has duration (it's not punctiliar). It is started
transactionally, and it ends transactionally, and inside of it, exchanges and
transfers happen transactionally (though the link between our db and our
processor's db could be tightened up; see #213). Exchanges immediately affect
the participant's balance, but transfers accrue against a "pending" column in
the database. Once the payday event has completed successfully, it ends with
the pending column being applied to the balance column and reset to NULL in a
single transaction.

"""
from __future__ import unicode_literals

from decimal import Decimal, ROUND_UP

import balanced
import stripe
import aspen.utils
from aspen import log
from aspen.utils import typecheck
from gittip.models.participant import Participant
from psycopg2 import IntegrityError


# Set fees and minimums.
# ======================
# Balanced has a $0.50 minimum. We go even higher to avoid onerous
# per-transaction fees. See:
# https://github.com/gittip/www.gittip.com/issues/167 XXX I should maybe
# compute this using *ahem* math.

FEE_CHARGE = ( Decimal("0.30")   # $0.30
             , Decimal("0.029")  #  2.9%
              )
FEE_CREDIT = Decimal("0.00")    # Balanced doesn't actually charge us for this,
                                # because we were in the door early enough.

MINIMUM_CHARGE = Decimal("9.41")
MINIMUM_CREDIT = Decimal("10.00")


def upcharge(amount):
    """Given an amount, return a higher amount and the difference.
    """
    typecheck(amount, Decimal)
    charge_amount = (amount + FEE_CHARGE[0]) / (1 - FEE_CHARGE[1])
    charge_amount = charge_amount.quantize(FEE_CHARGE[0], rounding=ROUND_UP)
    return charge_amount, charge_amount - amount

def skim_credit(amount):
    """Given an amount, return a lower amount and the difference.
    """
    typecheck(amount, Decimal)
    return amount - FEE_CREDIT, FEE_CREDIT

assert upcharge(MINIMUM_CHARGE) == (Decimal('10.00'), Decimal('0.59'))


def is_whitelisted(participant):
    """Given a dict, return bool, possibly logging.

    We only perform credit card charges and bank deposits for whitelisted
    participants. We don't even include is_suspicious participants in the
    initial SELECT, so we should never see one here.

    """
    assert participant.is_suspicious is not True, participant.username
    if participant.is_suspicious is None:
        log("UNREVIEWED: %s" % participant.username)
        return False
    return True


class NoPayday(Exception):
    def __str__(self):
        return "No payday found where one was expected."


class Payday(object):
    """Represent an abstract event during which money is moved.

    On Payday, we want to use a participant's Gittip balance to settle their
    tips due (pulling in more money via credit card as needed), but we only
    want to use their balance at the start of Payday. Balance changes should be
    atomic globally per-Payday.

    """

    def __init__(self, db):
        """Takes a postgres.Postgres instance.
        """
        self.db = db


    def genparticipants(self, ts_start, for_payday):
        """Generator to yield participants with tips and total.

        We re-fetch participants each time, because the second time through
        we want to use the total obligations they have for next week, and
        if we pass a non-False for_payday to get_tips_and_total then we
        only get unfulfilled tips from prior to that timestamp, which is
        none of them by definition.

        If someone changes tips after payout starts, and we crash during
        payout, then their new tips_and_total will be used on the re-run.
        That's okay.

        """
        for participant in self.get_participants(ts_start):
            tips, total = participant.get_tips_and_total(for_payday=for_payday)
            typecheck(total, Decimal)
            yield(participant, tips, total)


    def run(self):
        """This is the starting point for payday.

        This method runs every Thursday. It is structured such that it can be
        run again safely (with a newly-instantiated Payday object) if it
        crashes.

        """
        _start = aspen.utils.utcnow()
        log("Greetings, program! It's PAYDAY!!!!")
        ts_start = self.start()
        self.zero_out_pending(ts_start)

        self.payin(ts_start, self.genparticipants(ts_start, ts_start))
        self.move_pending_to_balance_for_teams()
        self.pachinko(ts_start, self.genparticipants(ts_start, ts_start))
        self.clear_pending_to_balance()
        self.payout(ts_start, self.genparticipants(ts_start, False))
        self.set_nactive(ts_start)

        self.end()

        _end = aspen.utils.utcnow()
        _delta = _end - _start
        fmt_past = "Script ran for {age} (%s)." % _delta

        # XXX For some reason newer versions of aspen use old string
        # formatting, so if/when we upgrade this will break. Why do we do that
        # in aspen, anyway?

        log(aspen.utils.to_age(_start, fmt_past=fmt_past))


    def start(self):
        """Try to start a new Payday.

        If there is a Payday that hasn't finished yet, then the UNIQUE
        constraint on ts_end will kick in and notify us of that. In that case
        we load the existing Payday and work on it some more. We use the start
        time of the current Payday to synchronize our work.

        """
        try:
            ts_start = self.db.one("INSERT INTO paydays DEFAULT VALUES "
                                   "RETURNING ts_start")
            log("Starting a new payday.")
        except IntegrityError:  # Collision, we have a Payday already.
            ts_start = self.db.one("""

                SELECT ts_start
                  FROM paydays
                 WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz

            """)
            log("Picking up with an existing payday.")

        log("Payday started at %s." % ts_start)
        return ts_start


    def zero_out_pending(self, ts_start):
        """Given a timestamp, zero out the pending column.

        We keep track of balance changes as a result of Payday in the pending
        column, and then move them over to the balance column in one big
        transaction at the end of Payday.

        """
        START_PENDING = """\

            UPDATE participants
               SET pending=0.00
             WHERE pending IS NULL
               AND claimed_time < %s

        """
        self.db.run(START_PENDING, (ts_start,))
        log("Zeroed out the pending column.")
        return None


    def get_participants(self, ts_start):
        """Given a timestamp, return a list of participants dicts.
        """
        PARTICIPANTS = """\
            SELECT participants.*::participants
              FROM participants
             WHERE claimed_time IS NOT NULL
               AND claimed_time < %s
               AND is_suspicious IS NOT true
          ORDER BY claimed_time ASC
        """
        participants = self.db.all(PARTICIPANTS, (ts_start,))
        log("Fetched participants.")
        return participants


    def payin(self, ts_start, participants):
        """Given a datetime and an iterator, do the payin side of Payday.
        """
        i = 0
        log("Starting payin loop.")
        for i, (participant, tips, total) in enumerate(participants, start=1):
            if i % 100 == 0:
                log("Payin done for %d participants." % i)
            self.charge_and_or_transfer(ts_start, participant, tips, total)
        log("Did payin for %d participants." % i)


    def pachinko(self, ts_start, participants):
        i = 0
        for i, (participant, foo, bar) in enumerate(participants, start=1):
            if i % 100 == 0:
                log("Pachinko done for %d participants." % i)
            if participant.number != 'plural':
                continue

            available = participant.balance
            log("Pachinko out from %s with $%s." % ( participant.username
                                                   , available
                                                    ))

            def tip(member, amount):
                tip = {}
                tip['tipper'] = participant.username
                tip['tippee'] = member['username']
                tip['amount'] = amount
                tip['claimed_time'] = ts_start
                self.tip( participant
                        , tip
                        , ts_start
                        , pachinko=True
                         )
                return tip['amount']

            for member in participant.get_members():
                amount = min(member['take'], available)
                available -= amount
                tip(member, amount)
                if available == 0:
                    break

        log("Did pachinko for %d participants." % i)


    def payout(self, ts_start, participants):
        """Given a datetime and an iterator, do the payout side of Payday.
        """
        i = 0
        log("Starting payout loop.")
        for i, (participant, tips, total) in enumerate(participants, start=1):
            if i % 100 == 0:
                log("Payout done for %d participants." % i)
            self.ach_credit(ts_start, participant, tips, total)
        log("Did payout for %d participants." % i)


    def charge_and_or_transfer(self, ts_start, participant, tips, total):
        """Given one participant record, pay their day.

        Charge each participants' credit card if needed before transfering
        money between Gittip accounts.

        """
        short = total - participant.balance
        if short > 0:

            # The participant's Gittip account is short the amount needed to
            # fund all their tips. Let's try pulling in money from their credit
            # card. If their credit card fails we'll forge ahead, in case they
            # have a positive Gittip balance already that can be used to fund
            # at least *some* tips. The charge method will have set
            # last_bill_result to a non-empty string if the card did fail.

            self.charge(participant, short)

        nsuccessful_tips = 0
        for tip in tips:
            result = self.tip(participant, tip, ts_start)
            if result >= 0:
                nsuccessful_tips += result
            else:
                break

        self.mark_participant(nsuccessful_tips)


    def move_pending_to_balance_for_teams(self):
        """Transfer pending into balance for teams.

        We do this because debit_participant operates against balance, not
        pending. This is because credit card charges go directly into balance
        on the first (payin) loop.

        """
        self.db.run("""\

            UPDATE participants
               SET balance = (balance + pending)
                 , pending = 0
             WHERE number='plural'

        """)
        # "Moved" instead of "cleared" because we don't also set to null.
        log("Moved pending to balance for teams. Ready for pachinko.")


    def clear_pending_to_balance(self):
        """Transfer pending into balance, setting pending to NULL.

        Any users that were created while the payin loop was running will have
        pending NULL (the default). If we try to add that to balance we'll get
        a NULL (0.0 + NULL = NULL), and balance has a NOT NULL constraint.
        Hence the where clause. See:

            https://github.com/gittip/www.gittip.com/issues/170

        """

        self.db.run("""\

            UPDATE participants
               SET balance = (balance + pending)
                 , pending = NULL
             WHERE pending IS NOT NULL

        """)
        # "Cleared" instead of "moved because we also set to null.
        log("Cleared pending to balance. Ready for payouts.")


    def set_nactive(self, ts_start):
        self.db.run("""\

            UPDATE paydays
               SET nactive=(
                    SELECT count(DISTINCT foo.*) FROM (
                        SELECT tipper FROM transfers WHERE "timestamp" >= %(ts_start)s
                            UNION
                        SELECT tippee FROM transfers WHERE "timestamp" >= %(ts_start)s
                    ) AS foo
                )
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz

        """, {'ts_start': ts_start})

    def end(self):
        self.db.one("""\

            UPDATE paydays
               SET ts_end=now()
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)


    # Move money between Gittip participants.
    # =======================================

    def tip(self, participant, tip, ts_start, pachinko=False):
        """Given dict, dict, and datetime, log and return int.

        Return values:

             0 if no valid tip available or tip has not been claimed
             1 if tip is valid
            -1 if transfer fails and we cannot continue

        """
        msg = "$%s from %s to %s%s."
        msg %= ( tip['amount']
               , participant.username
               , tip['tippee']
               , " (pachinko)" if pachinko else ""
                )

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

        if not self.transfer(participant.username, tip['tippee'], \
                                             tip['amount'], pachinko=pachinko):

            # The transfer failed due to a lack of funds for the participant.
            # Don't try any further transfers.

            log("FAILURE: %s" % msg)
            return -1

        log("SUCCESS: %s" % msg)
        return 1


    def transfer(self, tipper, tippee, amount, pachinko=False):
        """Given two unicodes, a Decimal, and a boolean, return a boolean.

        If the tipper doesn't have enough in their Gittip account then we
        return False. Otherwise we decrement tipper's balance and increment
        tippee's *pending* balance by amount.

        """
        typecheck( tipper, unicode
                 , tippee, unicode
                 , amount, Decimal
                 , pachinko, bool
                  )
        with self.db.get_cursor() as cursor:

            try:
                self.debit_participant(cursor, tipper, amount)
            except IntegrityError:
                return False

            self.credit_participant(cursor, tippee, amount)
            self.record_transfer(cursor, tipper, tippee, amount)
            if pachinko:
                self.mark_pachinko(cursor, amount)
            else:
                self.mark_transfer(cursor, amount)

            return True


    def debit_participant(self, cursor, participant, amount):
        """Decrement the tipper's balance.
        """

        DECREMENT = """\

           UPDATE participants
              SET balance=(balance - %s)
            WHERE username=%s
              AND pending IS NOT NULL
        RETURNING balance

        """

        # This will fail with IntegrityError if the balance goes below zero.
        # We catch that and return false in our caller.
        cursor.execute(DECREMENT, (amount, participant))

        rec = cursor.fetchone()
        assert rec is not None, (amount, participant)  # sanity check


    def credit_participant(self, cursor, participant, amount):
        """Increment the tippee's *pending* balance.

        The pending balance will clear to the balance proper when Payday is
        done.

        """

        INCREMENT = """\

           UPDATE participants
              SET pending=(pending + %s)
            WHERE username=%s
              AND pending IS NOT NULL
        RETURNING pending

        """
        cursor.execute(INCREMENT, (amount, participant))
        rec = cursor.fetchone()
        assert rec is not None, (participant, amount)  # sanity check


    # Move money between Gittip and the outside world.
    # ================================================

    def charge(self, participant, amount):
        """Given dict and Decimal, return None.

        This is the only place where we actually charge credit cards. Amount
        should be the nominal amount. We'll compute Gittip's fee below this
        function and add it to amount to end up with charge_amount.

        """
        typecheck(participant, Participant, amount, Decimal)

        username = participant.username
        balanced_account_uri = participant.balanced_account_uri
        stripe_customer_id = participant.stripe_customer_id

        typecheck( username, unicode
                 , balanced_account_uri, (unicode, None)
                 , stripe_customer_id, (unicode, None)
                  )


        # Perform some last-minute checks.
        # ================================

        if balanced_account_uri is None and stripe_customer_id is None:
            self.mark_missing_funding()
            return      # Participant has no funding source.

        if not is_whitelisted(participant):
            return      # Participant not trusted.


        # Go to Balanced or Stripe.
        # =========================

        if balanced_account_uri is not None:
            things = self.charge_on_balanced( username
                                            , balanced_account_uri
                                            , amount
                                             )
            charge_amount, fee, error = things
        else:
            assert stripe_customer_id is not None
            things = self.charge_on_stripe( username
                                          , stripe_customer_id
                                          , amount
                                           )
            charge_amount, fee, error = things

        amount = charge_amount - fee  # account for possible rounding under
                                      # charge_on_*

        self.record_charge( amount
                          , charge_amount
                          , fee
                          , error
                          , username
                           )


    def ach_credit(self, ts_start, participant, tips, total):

        # Compute the amount to credit them.
        # ==================================
        # Leave money in Gittip to cover their obligations next week (as these
        # currently stand). Also reduce the amount by our service fee.

        balance = participant.balance
        assert balance is not None, balance # sanity check
        amount = balance - total


        # Do some last-minute checks.
        # ===========================

        if amount <= 0:
            return      # Participant not owed anything.

        if amount < MINIMUM_CREDIT:
            also_log = ""
            if total > 0:
                also_log = " ($%s balance - $%s in obligations)"
                also_log %= (balance, total)
            log("Minimum payout is $%s. %s is only due $%s%s."
               % (MINIMUM_CREDIT, participant.username, amount, also_log))
            return      # Participant owed too little.

        if not is_whitelisted(participant):
            return      # Participant not trusted.


        # Do final calculations.
        # ======================

        credit_amount, fee = skim_credit(amount)
        cents = credit_amount * 100

        if total > 0:
            also_log = "$%s balance - $%s in obligations"
            also_log %= (balance, total)
        else:
            also_log = "$%s" % amount
        msg = "Crediting %s %d cents (%s - $%s fee = $%s) on Balanced ... "
        msg %= (participant.username, cents, also_log, fee, credit_amount)


        # Try to dance with Balanced.
        # ===========================

        try:

            balanced_account_uri = participant.balanced_account_uri
            if balanced_account_uri is None:
                log("%s has no balanced_account_uri."
                    % participant.username)
                return  # not in Balanced

            account = balanced.Account.find(balanced_account_uri)
            if 'merchant' not in account.roles:
                log("%s is not a merchant." % participant.username)
                return  # not a merchant

            account.credit(cents)

            error = ""
            log(msg + "succeeded.")
        except balanced.exc.HTTPError as err:
            error = err.message
            log(msg + "failed: %s" % error)

        self.record_credit(credit_amount, fee, error, participant.username)


    def charge_on_balanced(self, username, balanced_account_uri, amount):
        """We have a purported balanced_account_uri. Try to use it.
        """
        typecheck( username, unicode
                 , balanced_account_uri, unicode
                 , amount, Decimal
                  )

        cents, msg, charge_amount, fee = self._prep_hit(amount)
        msg = msg % (username, "Balanced")

        try:
            customer = balanced.Account.find(balanced_account_uri)
            customer.debit(cents, description=username)
            log(msg + "succeeded.")
            error = ""
        except balanced.exc.HTTPError as err:
            error = err.message
            log(msg + "failed: %s" % error)

        return charge_amount, fee, error


    def charge_on_stripe(self, username, stripe_customer_id, amount):
        """We have a purported stripe_customer_id. Try to use it.
        """
        typecheck( username, unicode
                 , stripe_customer_id, unicode
                 , amount, Decimal
                  )

        cents, msg, charge_amount, fee = self._prep_hit(amount)
        msg = msg % (username, "Stripe")

        try:
            stripe.Charge.create( customer=stripe_customer_id
                                , amount=cents
                                , description=username
                                , currency="USD"
                                 )
            log(msg + "succeeded.")
            error = ""
        except stripe.StripeError, err:
            error = err.message
            log(msg + "failed: %s" % error)

        return charge_amount, fee, error


    def _prep_hit(self, unrounded):
        """Takes an amount in dollars. Returns cents, etc.

        cents       This is passed to the payment processor charge API. This is
                    the value that is actually charged to the participant. It's
                    an int.
        msg         A log message with a couple %s to be filled in by the
                    caller.
        upcharged   Decimal dollar equivalent to `cents'.
        fee         Decimal dollar amount of the fee portion of `upcharged'.

        The latter two end up in the db in a couple places via record_charge.

        """
        also_log = ''
        rounded = unrounded
        if unrounded < MINIMUM_CHARGE:
            rounded = MINIMUM_CHARGE  # per github/#167
            also_log = ' [rounded up from $%s]' % unrounded

        upcharged, fee = upcharge(rounded)
        cents = int(upcharged * 100)

        msg = "Charging %%s %d cents ($%s%s + $%s fee = $%s) on %%s ... "
        msg %= cents, rounded, also_log, fee, upcharged

        return cents, msg, upcharged, fee


    # Record-keeping.
    # ===============

    def record_charge(self, amount, charge_amount, fee, error, username):
        """Given a Bunch of Stuff, return None.

        This function takes the result of an API call to a payment processor
        and records the result in our db. If the power goes out at this point
        then Postgres will be out of sync with the payment processor. We'll
        have to resolve that manually be reviewing the transaction log at the
        processor and modifying Postgres accordingly.

        For Balanced, this could be automated by generating an ID locally and
        commiting that to the db and then passing that through in the meta
        field.* Then syncing would be a case of simply:

            for payment in unresolved_payments:
                payment_in_balanced = balanced.Transaction.query.filter(
                  **{'meta.unique_id': 'value'}).one()
                payment.transaction_uri = payment_in_balanced.uri

        * https://www.balancedpayments.com/docs/meta

        """

        with self.db.get_cursor() as cursor:

            if error:
                last_bill_result = error
                amount = Decimal('0.00')
                self.mark_charge_failed(cursor)
            else:
                last_bill_result = ''
                EXCHANGE = """\

                        INSERT INTO exchanges
                               (amount, fee, participant)
                        VALUES (%s, %s, %s)

                """
                cursor.execute(EXCHANGE, (amount, fee, username))
                self.mark_charge_success(cursor, charge_amount, fee)


            # Update the participant's balance.
            # =================================
            # Credit card charges go immediately to balance, not to pending.

            RESULT = """\

            UPDATE participants
               SET last_bill_result=%s
                 , balance=(balance + %s)
             WHERE username=%s

            """
            cursor.execute(RESULT, (last_bill_result, amount, username))


    def record_credit(self, amount, fee, error, username):
        """Given a Bunch of Stuff, return None.

        Records in the exchanges table for credits have these characteristics:

            amount  It's negative, representing an outflow from Gittip to you.
                    This is oppositive of charges, where amount is positive.
                    The sign is how we differentiate the two in, e.g., the
                    history page.

            fee     It's positive, just like with charges.

        """
        credit = -amount  # From Gittip's POV this is money flowing out of the
                          # system.

        with self.db.get_cursor() as cursor:

            if error:
                last_ach_result = error
                credit = fee = Decimal('0.00')  # ensures balance won't change
                self.mark_ach_failed(cursor)
            else:
                last_ach_result = ''
                EXCHANGE = """\

                        INSERT INTO exchanges
                               (amount, fee, participant)
                        VALUES (%s, %s, %s)

                """
                cursor.execute(EXCHANGE, (credit, fee, username))
                self.mark_ach_success(cursor, amount, fee)


            # Update the participant's balance.
            # =================================

            RESULT = """\

            UPDATE participants
               SET last_ach_result=%s
                 , balance=(balance + %s)
             WHERE username=%s

            """
            cursor.execute(RESULT, ( last_ach_result
                                   , credit - fee     # -10.00 - 0.30 = -10.30
                                   , username
                                    ))


    def record_transfer(self, cursor, tipper, tippee, amount):
        cursor.run("""\

          INSERT INTO transfers
                      (tipper, tippee, amount)
               VALUES (%s, %s, %s)

        """, (tipper, tippee, amount))


    def mark_missing_funding(self):
        self.db.one("""\

            UPDATE paydays
               SET ncc_missing = ncc_missing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)


    def mark_charge_failed(self, cursor):
        STATS = """\

            UPDATE paydays
               SET ncc_failing = ncc_failing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """
        cursor.execute(STATS)
        assert cursor.fetchone() is not None

    def mark_charge_success(self, cursor, amount, fee):
        STATS = """\

            UPDATE paydays
               SET ncharges = ncharges + 1
                 , charge_volume = charge_volume + %s
                 , charge_fees_volume = charge_fees_volume + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """
        cursor.execute(STATS, (amount, fee))
        assert cursor.fetchone() is not None


    def mark_ach_failed(self, cursor):
        cursor.one("""\

            UPDATE paydays
               SET nach_failing = nach_failing + 1
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, default=NoPayday)

    def mark_ach_success(self, cursor, amount, fee):
        cursor.one("""\

            UPDATE paydays
               SET nachs = nachs + 1
                 , ach_volume = ach_volume + %s
                 , ach_fees_volume = ach_fees_volume + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, (-amount, fee), default=NoPayday)


    def mark_transfer(self, cursor, amount):
        cursor.one("""\

            UPDATE paydays
               SET ntransfers = ntransfers + 1
                 , transfer_volume = transfer_volume + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, (amount,), default=NoPayday)


    def mark_pachinko(self, cursor, amount):
        cursor.one("""\

            UPDATE paydays
               SET npachinko = npachinko + 1
                 , pachinko_volume = pachinko_volume + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, (amount,), default=NoPayday)


    def mark_participant(self, nsuccessful_tips):
        self.db.one("""\

            UPDATE paydays
               SET nparticipants = nparticipants + 1
                 , ntippers = ntippers + %s
                 , ntips = ntips + %s
             WHERE ts_end='1970-01-01T00:00:00+00'::timestamptz
         RETURNING id

        """, ( 1 if nsuccessful_tips > 0 else 0
             , nsuccessful_tips  # XXX bug?
              ), default=NoPayday)
