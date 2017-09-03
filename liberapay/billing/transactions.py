"""Functions for moving money into, out of, or between wallets.
"""
from __future__ import division, print_function, unicode_literals

from decimal import Decimal

from mangopay.exceptions import APIError
from mangopay.resources import (
    BankAccount, BankWirePayIn, BankWirePayOut, DirectPayIn, SettlementTransfer,
    Transaction, Transfer, Wallet,
)
from mangopay.utils import Money
from pando.utils import typecheck

from liberapay.billing.fees import skim_bank_wire, skim_credit, upcharge_card
from liberapay.constants import FEE_PAYOUT_WARN, QUARANTINE
from liberapay.exceptions import (
    NegativeBalance, NotEnoughWithdrawableMoney, PaydayIsRunning,
    FeeExceedsAmount, TransactionFeeTooHigh, TransferError,
    AccountSuspended, Redirect,
)
from liberapay.models import check_db
from liberapay.models.participant import Participant
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.utils import group_by, NS


Money.__eq__ = lambda a, b: isinstance(b, Money) and a.__dict__ == b.__dict__
Money.__repr__ = lambda m: '<Money Amount=%(amount)r Currency=%(currency)r>' % m.__dict__


QUARANTINE = '%s days' % QUARANTINE.days


def repr_error(o):
    r = o.ResultCode
    if r == '000000':
        return
    msg = getattr(o, 'ResultMessage', None)
    if msg:
        r += ': ' + msg
    return r


def repr_exception(e):
    if isinstance(e, APIError):
        return '%s %s' % (e.code, e.args[0])
    else:
        return repr(e)


def create_wallet(db, participant):
    w = Wallet()
    w.Owners = [participant.mangopay_user_id]
    w.Description = str(participant.id)
    w.Currency = 'EUR'
    w.save()
    db.run("""
        UPDATE participants
           SET mangopay_wallet_id = %s
         WHERE id = %s
    """, (w.Id, participant.id))
    participant.set_attributes(mangopay_wallet_id=w.Id)
    return w.Id


def test_hook():
    return


def payout(db, route, amount, ignore_high_fee=False):
    """Withdraw money to the specified bank account (`route`).
    """
    assert amount > 0
    assert route
    assert route.network == 'mango-ba'

    participant = route.participant
    if participant.is_suspended:
        raise AccountSuspended()

    payday = db.one("SELECT * FROM paydays WHERE ts_start > ts_end")
    if payday:
        raise PaydayIsRunning

    ba = BankAccount.get(route.address, user_id=participant.mangopay_user_id)

    # Do final calculations
    credit_amount, fee, vat = skim_credit(amount, ba)
    if credit_amount <= 0 and fee > 0:
        raise FeeExceedsAmount
    fee_percent = fee / amount
    if fee_percent > FEE_PAYOUT_WARN and not ignore_high_fee:
        raise TransactionFeeTooHigh(fee_percent, fee, amount)

    # Try to dance with MangoPay
    e_id = record_exchange(db, route, -credit_amount, fee, vat, participant, 'pre')
    payout = BankWirePayOut()
    payout.AuthorId = participant.mangopay_user_id
    payout.DebitedFunds = Money(int(amount * 100), 'EUR')
    payout.DebitedWalletId = participant.mangopay_wallet_id
    payout.Fees = Money(int(fee * 100), 'EUR')
    payout.BankAccountId = route.address
    payout.BankWireRef = str(e_id)
    payout.Tag = str(e_id)
    try:
        test_hook()
        payout.save()
        return record_exchange_result(db, e_id, payout.Status.lower(), repr_error(payout), participant)
    except Exception as e:
        error = repr_exception(e)
        return record_exchange_result(db, e_id, 'failed', error, participant)


def charge(db, route, amount, return_url):
    """Charge the given credit card (`route`).

    Amount should be the nominal amount. We'll compute fees below this function
    and add it to amount to end up with charge_amount.

    """
    typecheck(amount, Decimal)
    assert route
    assert route.network == 'mango-cc'

    participant = route.participant

    charge_amount, fee, vat = upcharge_card(amount)
    amount = charge_amount - fee

    if not participant.mangopay_wallet_id:
        create_wallet(db, participant)

    e_id = record_exchange(db, route, amount, fee, vat, participant, 'pre')
    payin = DirectPayIn()
    payin.AuthorId = participant.mangopay_user_id
    payin.CreditedWalletId = participant.mangopay_wallet_id
    payin.DebitedFunds = Money(int(charge_amount * 100), 'EUR')
    payin.CardId = route.address
    payin.SecureModeReturnURL = return_url
    payin.Fees = Money(int(fee * 100), 'EUR')
    payin.Tag = str(e_id)
    try:
        test_hook()
        payin.save()
    except Exception as e:
        error = repr_exception(e)
        return record_exchange_result(db, e_id, 'failed', error, participant)

    if payin.SecureModeRedirectURL:
        raise Redirect(payin.SecureModeRedirectURL)

    return record_exchange_result(db, e_id, payin.Status.lower(), repr_error(payin), participant)


def payin_bank_wire(db, participant, debit_amount):
    """Prepare to receive a bank wire payin.

    The amount should be how much the user intends to send, not how much will
    arrive in the wallet.
    """

    route = ExchangeRoute.from_network(participant, 'mango-bw')
    if not route:
        route = ExchangeRoute.insert(participant, 'mango-bw', 'x')

    amount, fee, vat = skim_bank_wire(debit_amount)

    if not participant.mangopay_wallet_id:
        create_wallet(db, participant)

    e_id = record_exchange(db, route, amount, fee, vat, participant, 'pre')
    payin = BankWirePayIn()
    payin.AuthorId = participant.mangopay_user_id
    payin.CreditedWalletId = participant.mangopay_wallet_id
    payin.DeclaredDebitedFunds = Money(int(debit_amount * 100), 'EUR')
    payin.DeclaredFees = Money(int(fee * 100), 'EUR')
    payin.Tag = str(e_id)
    try:
        test_hook()
        payin.save()
    except Exception as e:
        error = repr_exception(e)
        return None, record_exchange_result(db, e_id, 'failed', error, participant)

    e = record_exchange_result(db, e_id, payin.Status.lower(), repr_error(payin), participant)
    return payin, e


def record_payout_refund(db, payout_refund):
    orig_payout = BankWirePayOut.get(payout_refund.InitialTransactionId)
    e_origin = db.one("SELECT * FROM exchanges WHERE id = %s" % (orig_payout.Tag,))
    e_refund_id = db.one("SELECT id FROM exchanges WHERE refund_ref = %s", (e_origin.id,))
    if e_refund_id:
        # Already recorded
        return e_refund_id
    amount, fee, vat = -e_origin.amount, -e_origin.fee, -e_origin.vat
    assert payout_refund.DebitedFunds == Money(int(amount * 100), 'EUR')
    assert payout_refund.Fees == Money(int(fee * 100), 'EUR')
    route = ExchangeRoute.from_id(e_origin.route)
    participant = Participant.from_id(e_origin.participant)
    wallet_id = e_origin.wallet_id
    return db.one("""
        INSERT INTO exchanges
               (amount, fee, vat, participant, status, route, note, refund_ref, wallet_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
     RETURNING id
    """, (amount, fee, vat, participant.id, 'created', route.id, None, e_origin.id, wallet_id))


def record_exchange(db, route, amount, fee, vat, participant, status, error=None):
    """Given a Bunch of Stuff, return an int (exchange_id).

    Records in the exchanges table have these characteristics:

        amount  It's negative for credits (representing an outflow from
                Liberapay to you) and positive for charges.
                The sign is how we differentiate the two in, e.g., the
                history page.

        fee     The payment processor's fee. It's always positive.

        vat     The amount of VAT included in the fee. Always positive.

    """
    if participant.is_suspended:
        raise AccountSuspended()

    with db.get_cursor() as cursor:

        wallet_id = participant.mangopay_wallet_id
        e = cursor.one("""
            INSERT INTO exchanges
                   (amount, fee, vat, participant, status, route, note, wallet_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
         RETURNING *
        """, (amount, fee, vat, participant.id, status, route.id, error, wallet_id))

        if status == 'failed':
            propagate_exchange(cursor, participant, e, error, 0)
        elif amount < 0:
            amount -= fee
            propagate_exchange(cursor, participant, e, '', amount)

    return e.id


def record_exchange_result(db, exchange_id, status, error, participant):
    """Updates the status of an exchange.
    """
    with db.get_cursor() as cursor:
        e = cursor.one("""
            UPDATE exchanges e
               SET status=%(status)s
                 , note=%(error)s
             WHERE id=%(exchange_id)s
               AND status <> %(status)s
         RETURNING *
        """, locals())
        if not e:
            return
        assert participant.id == e.participant

        amount = e.amount
        if amount < 0:
            amount = -amount + max(e.fee, 0) if status == 'failed' else 0
        else:
            amount = amount - min(e.fee, 0) if status == 'succeeded' else 0
        propagate_exchange(cursor, participant, e, error, amount)

        return e


def propagate_exchange(cursor, participant, exchange, error, amount):
    """Propagates an exchange's result to the participant's balance.
    """
    new_balance = cursor.one("""
        UPDATE participants
           SET balance=(balance + %s)
         WHERE id=%s
     RETURNING balance
    """, (amount, participant.id))

    if amount < 0 and new_balance < 0:
        raise NegativeBalance

    wallet_id = participant.mangopay_wallet_id
    if amount < 0:
        bundles = cursor.all("""
            LOCK TABLE cash_bundles IN EXCLUSIVE MODE;
            SELECT b.*
              FROM cash_bundles b
              JOIN exchanges e ON e.id = b.origin
             WHERE b.owner = %s
               AND b.ts < now() - INTERVAL %s
               AND b.disputed IS NOT TRUE
               AND b.locked_for IS NULL
          ORDER BY b.owner = e.participant DESC, b.ts
        """, (participant.id, QUARANTINE))
        withdrawable = sum(b.amount for b in bundles)
        x = -amount
        if x > withdrawable:
            raise NotEnoughWithdrawableMoney(Money(withdrawable, 'EUR'))
        for b in bundles:
            if x >= b.amount:
                cursor.run("""
                    UPDATE cash_bundles
                       SET owner = NULL
                         , withdrawal = %s
                         , wallet_id = NULL
                     WHERE id = %s
                """, (exchange.id, b.id))
                x -= b.amount
                if x == 0:
                    break
            else:
                assert x > 0
                cursor.run("""
                    INSERT INTO cash_bundles
                                (owner, origin, ts, amount, withdrawal, wallet_id)
                         VALUES (NULL, %s, %s, %s, %s, NULL)
                """, (b.origin, b.ts, x, exchange.id))
                cursor.run("""
                    UPDATE cash_bundles
                       SET amount = (amount - %s)
                     WHERE id = %s
                """, (x, b.id))
                break
    elif amount > 0 and (exchange.amount < 0 or exchange.refund_ref):
        # failed withdrawal
        orig_exchange_id = exchange.refund_ref or exchange.id
        cursor.run("""
            UPDATE cash_bundles b
               SET owner = %(p_id)s
                 , withdrawal = NULL
                 , wallet_id = %(wallet_id)s
             WHERE withdrawal = %(e_id)s
        """, dict(p_id=participant.id, e_id=orig_exchange_id, wallet_id=wallet_id))
    elif amount > 0:
        cursor.run("""
            INSERT INTO cash_bundles
                        (owner, origin, amount, ts, wallet_id)
                 VALUES (%s, %s, %s, %s, %s)
        """, (participant.id, exchange.id, amount, exchange.timestamp, wallet_id))

    participant.set_attributes(balance=new_balance)

    if amount != 0:
        participant.update_giving_and_tippees(cursor)
        merge_cash_bundles(cursor, participant.id)


def transfer(db, tipper, tippee, amount, context, **kw):
    get = lambda id, col: db.one("SELECT {0} FROM participants WHERE id = %s".format(col), (id,))
    wallet_from = kw.get('tipper_wallet_id') or get(tipper, 'mangopay_wallet_id')
    wallet_to = kw.get('tippee_wallet_id') or get(tippee, 'mangopay_wallet_id')
    if not wallet_to:
        wallet_to = create_wallet(db, Participant.from_id(tippee))
    t_id = prepare_transfer(
        db, tipper, tippee, amount, context, wallet_from, wallet_to,
        team=kw.get('team'), invoice=kw.get('invoice'), bundles=kw.get('bundles'),
    )
    tr = Transfer()
    tr.AuthorId = kw.get('tipper_mango_id') or get(tipper, 'mangopay_user_id')
    tr.CreditedUserId = kw.get('tippee_mango_id') or get(tippee, 'mangopay_user_id')
    tr.CreditedWalletId = wallet_to
    tr.DebitedFunds = Money(int(amount * 100), 'EUR')
    tr.DebitedWalletId = wallet_from
    tr.Fees = Money(0, 'EUR')
    tr.Tag = str(t_id)
    tr.save()
    return record_transfer_result(db, t_id, tr), t_id


def prepare_transfer(db, tipper, tippee, amount, context, wallet_from, wallet_to,
                     team=None, invoice=None, **kw):
    with db.get_cursor() as cursor:
        transfer = cursor.one("""
            INSERT INTO transfers
                        (tipper, tippee, amount, context, team, invoice, status,
                         wallet_from, wallet_to)
                 VALUES (%s, %s, %s, %s, %s, %s, 'pre',
                         %s, %s)
              RETURNING *
        """, (tipper, tippee, amount, context, team, invoice, wallet_from, wallet_to))
        lock_bundles(cursor, transfer, **kw)
    return transfer.id


def lock_bundles(cursor, transfer, bundles=None, prefer_bundles_from=-1):
    assert transfer.status == 'pre'
    cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
    tipper, tippee = transfer.tipper, transfer.tippee
    bundles = bundles or cursor.all("""
        SELECT b.*
          FROM cash_bundles b
          JOIN exchanges e ON e.id = b.origin
         WHERE b.owner = %(tipper)s
           AND b.withdrawal IS NULL
           AND b.locked_for IS NULL
      ORDER BY b.origin = %(prefer_bundles_from)s DESC
             , e.participant = %(tippee)s DESC
             , b.ts
    """, locals())
    transferable = sum(b.amount for b in bundles)
    x = transfer.amount
    if x > transferable:
        raise NegativeBalance()
    for b in bundles:
        if x >= b.amount:
            cursor.run("""
                UPDATE cash_bundles
                   SET locked_for = %s
                 WHERE id = %s
            """, (transfer.id, b.id))
            x -= b.amount
            if x == 0:
                break
        else:
            cursor.run("""
                UPDATE cash_bundles
                   SET amount = (amount - %s)
                 WHERE id = %s;

                INSERT INTO cash_bundles
                            (owner, origin, amount, ts, locked_for, wallet_id)
                     VALUES (%s, %s, %s, %s, %s, %s);
            """, (x, b.id, transfer.tipper, b.origin, x, b.ts, transfer.id, b.wallet_id))
            break


def record_transfer_result(db, t_id, tr):
    error = repr_error(tr)
    status = tr.Status.lower()
    assert (not error) ^ (status == 'failed')
    return _record_transfer_result(db, t_id, status, error)


def _record_transfer_result(db, t_id, status, error=None):
    balance = None
    with db.get_cursor() as c:
        tipper, tippee, amount, wallet_to = c.one("""
            UPDATE transfers
               SET status = %s
                 , error = %s
             WHERE id = %s
         RETURNING tipper, tippee, amount, wallet_to
        """, (status, error, t_id))
        if status == 'succeeded':
            # Update the balances
            balance = c.one("""

                UPDATE participants
                   SET balance = balance + %(amount)s
                 WHERE id = %(tippee)s;

                UPDATE participants
                   SET balance = balance - %(amount)s
                 WHERE id = %(tipper)s
             RETURNING balance;

            """, locals())
            # Transfer the locked bundles to the recipient
            bundles = c.all("""
                UPDATE cash_bundles
                   SET owner = %s
                     , locked_for = NULL
                     , wallet_id = %s
                 WHERE owner = %s
                   AND locked_for = %s
             RETURNING *
            """, (tippee, wallet_to, tipper, t_id))
            bundles_sum = sum(b.amount for b in bundles)
            assert bundles_sum == amount
        else:
            # Unlock the bundles
            bundles = c.all("""
                UPDATE cash_bundles
                   SET locked_for = NULL
                 WHERE owner = %s
                   AND locked_for = %s
            """, (tipper, t_id))
    if balance is not None:
        merge_cash_bundles(db, tippee)
        return balance
    raise TransferError(error)


def lock_disputed_funds(cursor, exchange, amount):
    """Prevent money that is linked to a chargeback from being withdrawn.
    """
    if amount != exchange.amount + exchange.fee:
        raise NotImplementedError("partial disputes are not implemented")
    cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
    disputed_bundles = [NS(d._asdict()) for d in cursor.all("""
        UPDATE cash_bundles
           SET disputed = true
         WHERE origin = %s
     RETURNING *
    """, (exchange.id,))]
    disputed_bundles_sum = sum(b.amount for b in disputed_bundles)
    assert disputed_bundles_sum == exchange.amount
    original_owner = exchange.participant
    for b in disputed_bundles:
        if b.owner == original_owner:
            continue
        try_to_swap_bundle(cursor, b, original_owner)


def recover_lost_funds(db, exchange, lost_amount, repudiation_id):
    """Recover as much money as possible from a payin which has been reverted.
    """
    original_owner = exchange.participant
    # Try (again) to swap the disputed bundles
    with db.get_cursor() as cursor:
        cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
        disputed_bundles = [NS(d._asdict()) for d in cursor.all("""
            SELECT *
              FROM cash_bundles
             WHERE origin = %s
               AND disputed = true
        """, (exchange.id,))]
        bundles_sum = sum(b.amount for b in disputed_bundles)
        assert bundles_sum == lost_amount - exchange.fee
        for b in disputed_bundles:
            if b.owner == original_owner:
                continue
            try_to_swap_bundle(cursor, b, original_owner)
    # Move the funds back to the original wallet
    chargebacks_account = Participant.get_chargebacks_account()
    LiberapayOrg = Participant.from_username('LiberapayOrg')
    assert LiberapayOrg
    grouped = group_by(disputed_bundles, lambda b: (b.owner, b.withdrawal))
    for (owner, withdrawal), bundles in grouped.items():
        assert owner != chargebacks_account.id
        if owner == original_owner:
            continue
        amount = sum(b.amount for b in bundles)
        if owner is None:
            bundles = None
            withdrawer = db.one("SELECT participant FROM exchanges WHERE id = %s", (withdrawal,))
            payer = LiberapayOrg.id
            create_debt(db, withdrawer, payer, amount, exchange.id)
            create_debt(db, original_owner, withdrawer, amount, exchange.id)
        else:
            payer = owner
            create_debt(db, original_owner, payer, amount, exchange.id)
        transfer(db, payer, original_owner, amount, 'chargeback', bundles=bundles)
    # Add a debt for the fee
    create_debt(db, original_owner, LiberapayOrg.id, exchange.fee, exchange.id)
    # Send the funds to the credit wallet
    # We have to do a SettlementTransfer instead of a normal Transfer. The amount
    # can't exceed the original payin amount, so we can't settle the fee debt.
    original_owner = Participant.from_id(original_owner)
    t_id = prepare_transfer(
        db, original_owner.id, chargebacks_account.id, exchange.amount, 'chargeback',
        original_owner.mangopay_wallet_id, chargebacks_account.mangopay_wallet_id,
        prefer_bundles_from=exchange.id,
    )
    tr = SettlementTransfer()
    tr.AuthorId = original_owner.mangopay_user_id
    tr.CreditedUserId = chargebacks_account.mangopay_user_id
    tr.CreditedWalletId = chargebacks_account.mangopay_wallet_id
    tr.DebitedFunds = Money(int(exchange.amount * 100), 'EUR')
    tr.DebitedWalletId = original_owner.mangopay_wallet_id
    tr.Fees = Money(0, 'EUR')
    tr.RepudiationId = repudiation_id
    tr.Tag = str(t_id)
    tr.save()
    return record_transfer_result(db, t_id, tr)


def try_to_swap_bundle(cursor, b, original_owner):
    """Attempt to switch a disputed cash bundle with a "safe" one.
    """
    swappable_origin_bundles = [NS(d._asdict()) for d in cursor.all("""
        SELECT *
          FROM cash_bundles
         WHERE owner = %s
           AND disputed IS NOT TRUE
           AND locked_for IS NULL
      ORDER BY ts ASC
    """, (original_owner,))]
    try_to_swap_bundle_with(cursor, b, swappable_origin_bundles)
    merge_cash_bundles(cursor, original_owner)
    if b.withdrawal:
        withdrawer = cursor.one(
            "SELECT participant FROM exchanges WHERE id = %s", (b.withdrawal,)
        )
        swappable_recipient_bundles = [NS(d._asdict()) for d in cursor.all("""
            SELECT *
              FROM cash_bundles
             WHERE owner = %s
               AND disputed IS NOT TRUE
               AND locked_for IS NULL
          ORDER BY ts ASC, amount = %s DESC
        """, (withdrawer, b.amount))]
        # Note: we don't restrict the date in the query above, so a swapped
        # bundle can end up "withdrawn" before it was even created
        try_to_swap_bundle_with(cursor, b, swappable_recipient_bundles)
        merge_cash_bundles(cursor, withdrawer)
    else:
        merge_cash_bundles(cursor, b.owner)


def try_to_swap_bundle_with(cursor, b1, swappable_bundles):
    """Attempt to switch the disputed cash bundle `b1` with one (or more) from
    the `swappable_bundles` list.
    """
    for b2 in swappable_bundles:
        if b2.amount == b1.amount:
            swap_bundles(cursor, b1, b2)
            break
        elif b2.amount > b1.amount:
            # Split the swappable bundle in two, then do the swap
            b3 = split_bundle(cursor, b2, b1.amount)
            swap_bundles(cursor, b1, b3)
            break
        else:
            # Split the disputed bundle in two, then do the swap
            b3 = split_bundle(cursor, b1, b2.amount)
            swap_bundles(cursor, b2, b3)


def split_bundle(cursor, b, amount):
    """Cut a bundle in two.

    Returns the new second bundle, whose amount is `amount`.
    """
    assert b.amount > amount
    assert not b.locked_for
    b.amount = cursor.one("""
        UPDATE cash_bundles
           SET amount = (amount - %s)
         WHERE id = %s
     RETURNING amount
    """, (amount, b.id))
    return NS(cursor.one("""
        INSERT INTO cash_bundles
                    (owner, origin, amount, ts, withdrawal, disputed, wallet_id)
             VALUES (%s, %s, %s, %s, %s, %s, %s)
          RETURNING *;
    """, (b.owner, b.origin, amount, b.ts, b.withdrawal, b.disputed, b.wallet_id))._asdict())


def swap_bundles(cursor, b1, b2):
    """Switch the current locations of the two cash bundles `b1` and `b2`.
    """
    assert not b1.locked_for
    assert not b2.locked_for
    cursor.run("""
        UPDATE cash_bundles
           SET owner = %s
             , withdrawal = %s
             , wallet_id = %s
         WHERE id = %s;
        UPDATE cash_bundles
           SET owner = %s
             , withdrawal = %s
             , wallet_id = %s
         WHERE id = %s;
    """, (b2.owner, b2.withdrawal, b2.wallet_id, b1.id,
          b1.owner, b1.withdrawal, b1.wallet_id, b2.id))
    b1.owner, b2.owner = b2.owner, b1.owner
    b1.withdrawal, b2.withdrawal = b2.withdrawal, b1.withdrawal


def merge_cash_bundles(db, p_id):
    """Regroup cash bundles who have the same origin and current location.
    """
    return db.one("""
        LOCK TABLE cash_bundles IN EXCLUSIVE MODE;
        WITH regroup AS (
                 SELECT owner, origin, wallet_id, sum(amount) AS amount, max(ts) AS ts
                   FROM cash_bundles
                  WHERE owner = %s
                    AND disputed IS NOT TRUE
                    AND locked_for IS NULL
               GROUP BY owner, origin, wallet_id
                 HAVING count(*) > 1
             ),
             inserted AS (
                 INSERT INTO cash_bundles
                             (owner, origin, amount, ts, wallet_id)
                      SELECT owner, origin, amount, ts, wallet_id
                        FROM regroup
                   RETURNING *
             ),
             deleted AS (
                 DELETE
                   FROM cash_bundles b
                  USING regroup g
                  WHERE b.owner = g.owner
                    AND b.origin = g.origin
                    AND b.disputed IS NOT TRUE
                    AND b.locked_for IS NULL
                    AND b.wallet_id = g.wallet_id
              RETURNING b.*
             )
        SELECT (SELECT json_agg(d) FROM deleted d) AS before
             , (SELECT json_agg(i) FROM inserted i) AS after
    """, (p_id,))


def create_debt(db, debtor, creditor, amount, origin):
    return db.one("""
        INSERT INTO debts
                    (debtor, creditor, amount, status, origin)
             VALUES (%s, %s, %s, 'due', %s)
          RETURNING *
    """, (debtor, creditor, amount, origin))


def sync_with_mangopay(db):
    """We can get out of sync with MangoPay if record_exchange_result wasn't
    completed. This is where we fix that.
    """
    check_db(db)

    exchanges = db.all("SELECT * FROM exchanges WHERE status = 'pre'")
    for e in exchanges:
        p = Participant.from_id(e.participant)
        transactions = Transaction.all(user_id=p.mangopay_user_id)
        transactions = [x for x in transactions if x.Tag == str(e.id)]
        assert len(transactions) < 2
        if transactions:
            t = transactions[0]
            error = repr_error(t)
            status = t.Status.lower()
            assert (not error) ^ (status == 'failed')
            record_exchange_result(db, e.id, status, error, p)
        else:
            # The exchange didn't happen
            if e.amount < 0:
                # Mark it as failed if it was a credit
                record_exchange_result(db, e.id, 'failed', 'interrupted', p)
            else:
                # Otherwise forget about it
                db.run("DELETE FROM exchanges WHERE id=%s", (e.id,))

    transfers = db.all("SELECT * FROM transfers WHERE status = 'pre'")
    for t in transfers:
        tipper = Participant.from_id(t.tipper)
        transactions = Transaction.all(user_id=tipper.mangopay_user_id)
        transactions = [x for x in transactions if x.Type == 'TRANSFER' and x.Tag == str(t.id)]
        assert len(transactions) < 2
        if transactions:
            record_transfer_result(db, t.id, transactions[0])
        else:
            # The transfer didn't happen, remove it
            db.run("""
                UPDATE cash_bundles
                   SET locked_for = NULL
                 WHERE owner = %s
                   AND locked_for = %s
            """, (t.tipper, t.id))
            db.run("DELETE FROM transfers WHERE id = %s", (t.id,))

    check_db(db)
