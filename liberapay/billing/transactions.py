"""Functions for moving money into, out of, or between wallets.
"""
from __future__ import division, print_function, unicode_literals

from decimal import Decimal
from time import sleep

from mangopay.exceptions import APIError
from mangopay.resources import (
    BankAccount, BankWirePayIn, BankWirePayOut, DirectPayIn, DirectDebitDirectPayIn,
    SettlementTransfer, Transfer, User, Wallet,
)
from mangopay.utils import Money

from liberapay.billing.fees import (
    skim_bank_wire, skim_credit, upcharge_card, upcharge_direct_debit
)
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


def create_wallet(db, participant, currency):
    w = Wallet()
    w.Owners = [participant.mangopay_user_id]
    w.Description = str(participant.id)
    w.Currency = currency
    w.save()
    return db.one("""
        INSERT INTO wallets
                    (remote_id, balance, owner, remote_owner_id)
             VALUES (%s, %s, %s, %s)
          RETURNING *
    """, (w.Id, w.Balance, participant.id, participant.mangopay_user_id))


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
    amount = Money(amount, 'EUR') if isinstance(amount, Decimal) else amount
    credit_amount, fee, vat = skim_credit(amount, ba)
    if credit_amount <= 0 and fee > 0:
        raise FeeExceedsAmount
    fee_percent = fee / amount
    if fee_percent > FEE_PAYOUT_WARN and not ignore_high_fee:
        raise TransactionFeeTooHigh(fee_percent, fee, amount)

    # Try to dance with MangoPay
    e_id = record_exchange(db, route, -credit_amount, fee, vat, participant, 'pre').id
    payout = BankWirePayOut()
    payout.AuthorId = participant.mangopay_user_id
    payout.DebitedFunds = amount.int()
    payout.DebitedWalletId = participant.get_current_wallet(amount.currency).remote_id
    payout.Fees = fee.int()
    payout.BankAccountId = route.address
    payout.BankWireRef = str(e_id)
    payout.Tag = str(e_id)
    try:
        test_hook()
        payout.save()
        return record_exchange_result(
            db, e_id, payout.Id, payout.Status.lower(), repr_error(payout), participant
        )
    except Exception as e:
        error = repr_exception(e)
        return record_exchange_result(db, e_id, '', 'failed', error, participant)


def charge(db, route, amount, return_url):
    """Charge the given credit card (`route`).

    Amount should be the nominal amount. We'll compute fees below this function
    and add it to amount to end up with charge_amount.

    """
    assert isinstance(amount, (Decimal, Money)), type(amount)
    assert route
    assert route.network == 'mango-cc'

    participant = route.participant

    amount = Money(amount, 'EUR') if isinstance(amount, Decimal) else amount
    charge_amount, fee, vat = upcharge_card(amount)
    amount = charge_amount - fee

    wallet = participant.get_current_wallet(amount.currency, create=True)
    e_id = record_exchange(db, route, amount, fee, vat, participant, 'pre').id
    payin = DirectPayIn()
    payin.AuthorId = participant.mangopay_user_id
    payin.CreditedWalletId = wallet.remote_id
    payin.DebitedFunds = charge_amount.int()
    payin.CardId = route.address
    payin.SecureModeReturnURL = return_url
    payin.Fees = fee.int()
    payin.Tag = str(e_id)
    try:
        test_hook()
        payin.save()
    except Exception as e:
        error = repr_exception(e)
        return record_exchange_result(db, e_id, '', 'failed', error, participant)

    if payin.SecureModeRedirectURL:
        raise Redirect(payin.SecureModeRedirectURL)

    return record_exchange_result(
        db, e_id, payin.Id, payin.Status.lower(), repr_error(payin), participant
    )


def prepare_direct_debit(db, route, amount):
    """Prepare to debit a bank account.
    """
    assert isinstance(amount, (Decimal, Money)), type(amount)

    assert route.network == 'mango-ba'

    participant = route.participant

    amount = Money(amount, 'EUR') if isinstance(amount, Decimal) else amount
    debit_amount, fee, vat = upcharge_direct_debit(amount)
    amount = debit_amount - fee

    status = 'pre' if route.mandate else 'pre-mandate'
    return record_exchange(db, route, amount, fee, vat, participant, status)


def execute_direct_debit(db, exchange, route):
    """Execute a prepared direct debit.
    """
    assert exchange.route == route.id
    assert route
    assert route.network == 'mango-ba'
    assert route.mandate

    participant = route.participant
    assert exchange.participant == participant.id

    if exchange.status == 'pre-mandate':
        exchange = db.one("""
            UPDATE exchanges
               SET status = 'pre'
             WHERE id = %s
               AND status = %s
         RETURNING *
        """, (exchange.id, exchange.status))
        assert exchange, 'race condition'

    assert exchange.status == 'pre'

    amount, fee = exchange.amount, exchange.fee
    debit_amount = amount + fee

    e_id = exchange.id
    payin = DirectDebitDirectPayIn()
    payin.AuthorId = participant.mangopay_user_id
    payin.CreditedWalletId = exchange.wallet_id
    payin.DebitedFunds = debit_amount.int()
    payin.MandateId = route.mandate
    payin.Fees = fee.int()
    payin.Tag = str(e_id)
    try:
        test_hook()
        payin.save()
    except Exception as e:
        error = repr_exception(e)
        return record_exchange_result(db, e_id, '', 'failed', error, participant)

    return record_exchange_result(
        db, e_id, payin.Id, payin.Status.lower(), repr_error(payin), participant
    )


def payin_bank_wire(db, participant, debit_amount):
    """Prepare to receive a bank wire payin.

    The amount should be how much the user intends to send, not how much will
    arrive in the wallet.
    """

    route = ExchangeRoute.upsert_bankwire_route(participant)

    if not isinstance(debit_amount, Money):
        debit_amount = Money(debit_amount, 'EUR')
    amount, fee, vat = skim_bank_wire(debit_amount)

    wallet = participant.get_current_wallet(amount.currency, create=True)
    e_id = record_exchange(db, route, amount, fee, vat, participant, 'pre').id
    payin = BankWirePayIn()
    payin.AuthorId = participant.mangopay_user_id
    payin.CreditedWalletId = wallet.remote_id
    payin.DeclaredDebitedFunds = debit_amount.int()
    payin.DeclaredFees = fee.int()
    payin.Tag = str(e_id)
    try:
        test_hook()
        payin.save()
    except Exception as e:
        error = repr_exception(e)
        return None, record_exchange_result(db, e_id, '', 'failed', error, participant)

    e = record_exchange_result(
        db, e_id, payin.Id, payin.Status.lower(), repr_error(payin), participant
    )
    return payin, e


def cancel_bank_wire_payin(db, exchange, payin, participant):
    record_exchange_result(db, exchange.id, payin.Id, 'failed', "canceled", participant)


def record_unexpected_payin(db, payin):
    """Record an unexpected bank wire payin.
    """
    assert payin.PaymentType == 'BANK_WIRE'
    debited_amount = payin.DebitedFunds / Decimal(100)
    paid_fee = payin.Fees / Decimal(100)
    vat = skim_bank_wire(debited_amount)[2]
    wallet_id = payin.CreditedWalletId
    participant = Participant.from_mangopay_user_id(payin.AuthorId)
    current_wallet = participant.get_current_wallet(debited_amount.currency)
    assert current_wallet.remote_id == wallet_id
    route = ExchangeRoute.upsert_bankwire_route(participant)
    amount = debited_amount - paid_fee
    return db.one("""
        INSERT INTO exchanges
               (amount, fee, vat, participant, status, route, note, remote_id, wallet_id)
        VALUES (%s, %s, %s, %s, 'created', %s, NULL, %s, %s)
     RETURNING id
    """, (amount, paid_fee, vat, participant.id, route.id, payin.Id, wallet_id))


def record_payout_refund(db, payout_refund):
    orig_payout = BankWirePayOut.get(payout_refund.InitialTransactionId)
    e_origin = db.one("SELECT * FROM exchanges WHERE id = %s", (orig_payout.Tag,))
    e_refund_id = db.one("SELECT id FROM exchanges WHERE refund_ref = %s", (e_origin.id,))
    if e_refund_id:
        # Already recorded
        return e_refund_id
    amount, fee, vat = -e_origin.amount, -e_origin.fee, -e_origin.vat
    assert payout_refund.DebitedFunds / 100 == amount
    assert payout_refund.Fees / 100 == fee
    route = ExchangeRoute.from_id(e_origin.route)
    participant = Participant.from_id(e_origin.participant)
    remote_id = payout_refund.Id
    wallet_id = e_origin.wallet_id
    return db.one("""
        INSERT INTO exchanges
               (amount, fee, vat, participant, status, route, note, refund_ref, remote_id, wallet_id)
        VALUES (%s, %s, %s, %s, 'created', %s, NULL, %s, %s, %s)
     RETURNING id
    """, (amount, fee, vat, participant.id, route.id, e_origin.id, remote_id, wallet_id))


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
    assert status.startswith('pre')
    if participant.is_suspended:
        raise AccountSuspended()

    with db.get_cursor() as cursor:

        wallet_id = participant.get_current_wallet(amount.currency, create=True).remote_id
        e = cursor.one("""
            INSERT INTO exchanges
                   (amount, fee, vat, participant, status, route, note, wallet_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
         RETURNING *
        """, (amount, fee, vat, participant.id, status, route.id, error, wallet_id))

        if amount < 0:
            amount -= fee
            propagate_exchange(cursor, participant, e, '', amount)

    return e


def record_exchange_result(db, exchange_id, remote_id, status, error, participant):
    """Updates the status of an exchange.
    """
    with db.get_cursor() as cursor:
        e = cursor.one("""
            UPDATE exchanges e
               SET status=%(status)s
                 , note=%(error)s
                 , remote_id=%(remote_id)s
             WHERE id=%(exchange_id)s
               AND status <> %(status)s
         RETURNING *
        """, locals())
        if not e:
            return
        assert participant.id == e.participant

        amount = e.amount
        if amount < 0:
            amount = -amount + max(e.fee, 0) if status == 'failed' else amount.zero()
        else:
            amount = amount - min(e.fee, 0) if status == 'succeeded' else amount.zero()
        propagate_exchange(cursor, participant, e, error, amount)

        return e


def propagate_exchange(cursor, participant, exchange, error, amount):
    """Propagates an exchange's result to the participant's balance.
    """
    wallet_id = exchange.wallet_id
    new_balance = cursor.one("""
        UPDATE wallets
           SET balance = (balance + %s)
         WHERE remote_id = %s
           AND (balance + %s) >= 0
     RETURNING balance
    """, (amount, wallet_id, amount))

    if new_balance is None:
        raise NegativeBalance

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
               AND b.amount::currency = %s
          ORDER BY b.owner = e.participant DESC, b.ts
        """, (participant.id, QUARANTINE, amount.currency))
        withdrawable = sum(b.amount for b in bundles)
        x = -amount
        if x > withdrawable:
            raise NotEnoughWithdrawableMoney(withdrawable)
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

    new_balance = cursor.one("SELECT recompute_balance(%s)", (participant.id,))
    participant.set_attributes(balance=new_balance)

    if amount != 0:
        merge_cash_bundles(cursor, participant.id)
        participant.update_giving_and_tippees(cursor)


def transfer(db, tipper, tippee, amount, context, **kw):
    tipper_wallet = NS(remote_id=kw.get('tipper_wallet_id'), remote_owner_id=kw.get('tipper_mango_id'))
    if not all(tipper_wallet.__dict__.values()):
        tipper_wallet = Participant.from_id(tipper).get_current_wallet(amount.currency)
    tippee_wallet = NS(remote_id=kw.get('tippee_wallet_id'), remote_owner_id=kw.get('tippee_mango_id'))
    if not all(tippee_wallet.__dict__.values()):
        tippee_wallet = Participant.from_id(tippee).get_current_wallet(amount.currency, create=True)
    wallet_from = tipper_wallet.remote_id
    wallet_to = tippee_wallet.remote_id
    t_id = prepare_transfer(
        db, tipper, tippee, amount, context, wallet_from, wallet_to,
        team=kw.get('team'), invoice=kw.get('invoice'), bundles=kw.get('bundles'),
    )
    tr = Transfer()
    tr.AuthorId = tipper_wallet.remote_owner_id
    tr.CreditedUserId = tippee_wallet.remote_owner_id
    tr.CreditedWalletId = wallet_to
    tr.DebitedFunds = amount.int()
    tr.DebitedWalletId = wallet_from
    tr.Fees = Money(0, amount.currency)
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
    currency = transfer.amount.currency
    bundles = bundles or cursor.all("""
        SELECT b.*
          FROM cash_bundles b
          JOIN exchanges e ON e.id = b.origin
         WHERE b.owner = %(tipper)s
           AND b.withdrawal IS NULL
           AND b.locked_for IS NULL
           AND b.amount::currency = %(currency)s
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
    r = _record_transfer_result(db, t_id, status, error)
    if status == 'failed':
        raise TransferError(error)
    return r


def _record_transfer_result(db, t_id, status, error=None):
    balance = None
    with db.get_cursor() as c:
        tipper, tippee, amount, wallet_from, wallet_to = c.one("""
            UPDATE transfers
               SET status = %s
                 , error = %s
             WHERE id = %s
         RETURNING tipper, tippee, amount, wallet_from, wallet_to
        """, (status, error, t_id))
        if status == 'succeeded':
            # Update the balances
            balance = c.one("""

                UPDATE wallets
                   SET balance = balance + %(amount)s
                 WHERE remote_id = %(wallet_to)s;

                UPDATE wallets
                   SET balance = balance - %(amount)s
                 WHERE remote_id = %(wallet_from)s;

                SELECT recompute_balance(%(tippee)s);
                SELECT recompute_balance(%(tipper)s);

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
        else:
            # Unlock the bundles
            bundles = c.all("""
                UPDATE cash_bundles
                   SET locked_for = NULL
                 WHERE owner = %s
                   AND locked_for = %s
             RETURNING *
            """, (tipper, t_id))
        bundles_sum = sum(b.amount for b in bundles)
        assert bundles_sum == amount
    merge_cash_bundles(db, tippee)
    return balance


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
    currency = exchange.amount.currency
    chargebacks_account, credit_wallet = Participant.get_chargebacks_account(currency)
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
    from_wallet = original_owner.get_current_wallet(currency).remote_id
    to_wallet = credit_wallet.remote_id
    t_id = prepare_transfer(
        db, original_owner.id, chargebacks_account.id, exchange.amount, 'chargeback',
        from_wallet, to_wallet, prefer_bundles_from=exchange.id,
    )
    tr = SettlementTransfer()
    tr.AuthorId = original_owner.mangopay_user_id
    tr.CreditedUserId = chargebacks_account.mangopay_user_id
    tr.CreditedWalletId = to_wallet
    tr.DebitedFunds = exchange.amount.int()
    tr.DebitedWalletId = from_wallet
    tr.Fees = Money(0, currency)
    tr.RepudiationId = repudiation_id
    tr.Tag = str(t_id)
    tr.save()
    return record_transfer_result(db, t_id, tr)


def try_to_swap_bundle(cursor, b, original_owner):
    """Attempt to switch a disputed cash bundle with a "safe" one.
    """
    currency = b.amount.currency
    swappable_origin_bundles = [NS(d._asdict()) for d in cursor.all("""
        SELECT *
          FROM cash_bundles
         WHERE owner = %s
           AND disputed IS NOT TRUE
           AND locked_for IS NULL
           AND amount::currency = %s
      ORDER BY ts ASC
    """, (original_owner, currency))]
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
               AND amount::currency = %s
          ORDER BY ts ASC, amount = %s DESC
        """, (withdrawer, currency, b.amount))]
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

    exchanges = db.all("""
        SELECT *, (e.timestamp < current_timestamp - interval '1 day') AS is_old
          FROM exchanges e
         WHERE e.status = 'pre'
    """)
    for e in exchanges:
        p = Participant.from_id(e.participant)
        transactions = [x for x in User(id=p.mangopay_user_id).transactions.all(
            Sort='CreationDate:DESC', Type=('PAYIN' if e.amount > 0 else 'PAYOUT')
        ) if x.Tag == str(e.id)]
        assert len(transactions) < 2
        if transactions:
            t = transactions[0]
            error = repr_error(t)
            status = t.Status.lower()
            assert (not error) ^ (status == 'failed')
            record_exchange_result(db, e.id, t.Id, status, error, p)
        elif e.is_old:
            # The exchange didn't happen, mark it as failed
            record_exchange_result(db, e.id, '', 'failed', 'interrupted', p)

    transfers = db.all("""
        SELECT *, (t.timestamp < current_timestamp - interval '1 day') AS is_old
          FROM transfers t
         WHERE t.status = 'pre'
    """)
    for t in transfers:
        tipper = Participant.from_id(t.tipper)
        transactions = [x for x in User(id=tipper.mangopay_user_id).transactions.all(
            Sort='CreationDate:DESC', Type='TRANSFER'
        ) if x.Tag == str(t.id)]
        assert len(transactions) < 2
        if transactions:
            record_transfer_result(db, t.id, transactions[0])
        elif t.is_old:
            # The transfer didn't happen, mark it as failed
            _record_transfer_result(db, t.id, 'failed', 'interrupted')

    check_db(db)


def check_wallet_balance(w, state={}):
    remote_wallet = Wallet.get(w.remote_id)
    remote_balance = remote_wallet.balance / 100
    try:
        assert remote_balance == w.balance, (
            "balances don't match for user #%s (liberapay id %s), wallet #%s contains %s, we expected %s" %
            (w.remote_owner_id, w.owner, w.remote_id, remote_balance, w.balance)
        )
    except AssertionError as e:
        from liberapay.website import website
        website.tell_sentry(e, state, allow_reraise=False)


def check_all_balances():
    from liberapay.website import website
    wallets = website.db.all("""
        SELECT *
          FROM wallets
         WHERE NOT remote_id LIKE 'CREDIT_%'
    """)
    for w in wallets:
        check_wallet_balance(w)
        sleep(0.1)
