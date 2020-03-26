"""Functions for moving money into, out of, or between wallets.
"""

from decimal import Decimal
from time import sleep
from types import SimpleNamespace

from mangopay.exceptions import APIError
from mangopay.resources import (
    BankAccount, BankWirePayIn, BankWirePayOut, DirectPayIn, DirectDebitDirectPayIn,
    PayInRefund, SettlementTransfer, Transfer, TransferRefund, User, Wallet,
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
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.utils import group_by


QUARANTINE = '%s days' % QUARANTINE.days


def Money_to_cents(m):
    r = Money(currency=m.currency)
    r.amount = int(m.amount * 100)
    return r


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
        if isinstance(e.content, dict) and e.content.get('errors'):
            errors = ' | '.join('%s (%s)' % (v, k) for k, v in e.content['errors'].items())
            return '%s | Error ID: %s' % (errors, e.content['Id'])
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
    payout.DebitedFunds = Money_to_cents(amount)
    payout.DebitedWalletId = participant.get_current_wallet(amount.currency).remote_id
    payout.Fees = Money_to_cents(fee)
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


def charge(db, route, amount, return_url, billing_address=None):
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
    if billing_address:
        payin.Billing = {'Address': billing_address}
    payin.CreditedWalletId = wallet.remote_id
    payin.DebitedFunds = Money_to_cents(charge_amount)
    payin.CardId = route.address
    payin.SecureMode = 'FORCE'
    payin.SecureModeReturnURL = return_url
    payin.Fees = Money_to_cents(fee)
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
    payin.DebitedFunds = Money_to_cents(debit_amount)
    payin.MandateId = route.mandate
    payin.Fees = Money_to_cents(fee)
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

    route = ExchangeRoute.upsert_generic_route(participant, 'mango-bw')

    if not isinstance(debit_amount, Money):
        debit_amount = Money(debit_amount, 'EUR')
    amount, fee, vat = skim_bank_wire(debit_amount)

    wallet = participant.get_current_wallet(amount.currency, create=True)
    e_id = record_exchange(db, route, amount, fee, vat, participant, 'pre').id
    payin = BankWirePayIn()
    payin.AuthorId = participant.mangopay_user_id
    payin.CreditedWalletId = wallet.remote_id
    payin.DeclaredDebitedFunds = Money_to_cents(debit_amount)
    payin.DeclaredFees = Money_to_cents(fee)
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
    participant = db.Participant.from_mangopay_user_id(payin.AuthorId)
    current_wallet = participant.get_current_wallet(debited_amount.currency)
    assert current_wallet.remote_id == wallet_id
    route = ExchangeRoute.upsert_generic_route(participant, 'mango-bw')
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
    participant = db.Participant.from_id(e_origin.participant)
    route = ExchangeRoute.from_id(participant, e_origin.route)
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
            delta = amount - fee
            cursor.run("""
                INSERT INTO exchange_events
                       (timestamp, exchange, status, error, wallet_delta)
                VALUES (current_timestamp, %s, %s, NULL, %s)
            """, (e.id, status, delta))
            propagate_exchange(cursor, participant, e, '', delta)

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
            return cursor.one("SELECT * FROM exchanges WHERE id = %s", (exchange_id,))
        assert participant.id == e.participant

        amount = e.amount
        if amount < 0:
            delta = -amount + max(e.fee, 0) if status == 'failed' else amount.zero()
        else:
            delta = amount - min(e.fee, 0) if status == 'succeeded' else amount.zero()
        propagate_exchange(cursor, participant, e, error, delta)

        if status != 'created':
            cursor.run("""
                INSERT INTO exchange_events
                       (timestamp, exchange, status, error, wallet_delta)
                VALUES (current_timestamp, %s, %s, %s, %s)
            """, (exchange_id, status, error, delta))

        return e


def propagate_exchange(cursor, participant, exchange, error, amount, bundles=None):
    """Propagates an exchange's result to the participant's balance.
    """
    cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")

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
        refund_ref = exchange.refund_ref or -1
        if bundles:
            # Refetch the bundles to ensure validity and prevent race conditions
            bundles = cursor.all("""
                SELECT b.*
                  FROM cash_bundles b
                  JOIN exchanges e ON e.id = b.origin
                 WHERE b.owner = %s
                   AND b.locked_for IS NULL
                   AND b.amount::currency = %s
                   AND b.id IN %s
              ORDER BY b.origin = %s DESC
                     , b.owner = e.participant DESC
                     , b.ts
            """, (participant.id, amount.currency, tuple(bundles), refund_ref))
        else:
            bundles = cursor.all("""
                SELECT b.*
                  FROM cash_bundles b
                  JOIN exchanges e ON e.id = b.origin
                 WHERE b.owner = %s
                   AND b.ts < now() - INTERVAL %s
                   AND b.disputed IS NOT TRUE
                   AND b.locked_for IS NULL
                   AND b.amount::currency = %s
              ORDER BY b.origin = %s DESC
                     , b.owner = e.participant DESC
                     , b.ts
            """, (participant.id, QUARANTINE, amount.currency, refund_ref))
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
        if exchange.refund_ref and exchange.status == 'succeeded':
            # payout refund
            orig_exchange_id = exchange.refund_ref
        else:
            # failed payout or payin refund
            orig_exchange_id = exchange.id
        bundles = cursor.all("""
            UPDATE cash_bundles b
               SET owner = %(p_id)s
                 , withdrawal = NULL
                 , wallet_id = %(wallet_id)s
             WHERE withdrawal = %(e_id)s
         RETURNING b.*
        """, dict(p_id=participant.id, e_id=orig_exchange_id, wallet_id=wallet_id))
        assert sum(b.amount for b in bundles) == amount
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
    tipper_wallet = SimpleNamespace(
        remote_id=kw.get('tipper_wallet_id'),
        remote_owner_id=kw.get('tipper_mango_id')
    )
    if not all(tipper_wallet.__dict__.values()):
        tipper_wallet = db.Participant.from_id(tipper).get_current_wallet(amount.currency)
    tippee_wallet = SimpleNamespace(
        remote_id=kw.get('tippee_wallet_id'),
        remote_owner_id=kw.get('tippee_mango_id')
    )
    if not all(tippee_wallet.__dict__.values()):
        tippee_wallet = db.Participant.from_id(tippee).get_current_wallet(amount.currency, create=True)
    wallet_from = tipper_wallet.remote_id
    wallet_to = tippee_wallet.remote_id
    t_id = prepare_transfer(
        db, tipper, tippee, amount, context, wallet_from, wallet_to,
        team=kw.get('team'), invoice=kw.get('invoice'), bundles=kw.get('bundles'),
        unit_amount=kw.get('unit_amount'),
    )
    tr = Transfer()
    tr.AuthorId = tipper_wallet.remote_owner_id
    tr.CreditedUserId = tippee_wallet.remote_owner_id
    tr.CreditedWalletId = wallet_to
    tr.DebitedFunds = Money_to_cents(amount)
    tr.DebitedWalletId = wallet_from
    tr.Fees = Money(0, amount.currency)
    tr.Tag = str(t_id)
    return execute_transfer(db, t_id, tr), t_id


def prepare_transfer(db, tipper, tippee, amount, context, wallet_from, wallet_to,
                     team=None, invoice=None, counterpart=None, refund_ref=None,
                     unit_amount=None, **kw):
    with db.get_cursor() as cursor:
        cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
        transfer = cursor.one("""
            INSERT INTO transfers
                        (tipper, tippee, amount, context, team, invoice, status,
                         wallet_from, wallet_to, counterpart, refund_ref, unit_amount)
                 VALUES (%s, %s, %s, %s, %s, %s, 'pre',
                         %s, %s, %s, %s, %s)
              RETURNING *
        """, (tipper, tippee, amount, context, team, invoice,
              wallet_from, wallet_to, counterpart, refund_ref, unit_amount))
        lock_bundles(cursor, transfer, **kw)
    return transfer.id


def lock_bundles(cursor, transfer, bundles=None, prefer_bundles_from=-1):
    assert transfer.status == 'pre'
    tipper, tippee = transfer.tipper, transfer.tippee
    currency = transfer.amount.currency
    if bundles:
        # Refetch the bundles to ensure validity and prevent race conditions
        bundles = tuple(bundles)
        bundles = cursor.all("""
            SELECT b.*
              FROM cash_bundles b
             WHERE b.owner = %(tipper)s
               AND b.withdrawal IS NULL
               AND b.locked_for IS NULL
               AND b.amount::currency = %(currency)s
               AND b.id IN %(bundles)s
          ORDER BY b.ts
        """, locals())
    else:
        bundles = cursor.all("""
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


def initiate_transfer(db, t_id):
    amount, status = db.one("""
        SELECT t.amount, t.status
          FROM transfers t
         WHERE t.id = %s
           AND t.status = 'pre'
    """, (t_id,))
    assert status == 'pre', (t_id, status)
    tipper_wallet = db.one("""
        SELECT w.remote_id, w.remote_owner_id
          FROM transfers t
          JOIN wallets w ON w.remote_id = t.wallet_from
         WHERE t.id = %s
    """, (t_id,))
    tippee_wallet = db.one("""
        SELECT w.remote_id, w.remote_owner_id
          FROM transfers t
          JOIN wallets w ON w.remote_id = t.wallet_to
         WHERE t.id = %s
    """, (t_id,))
    tr = Transfer()
    tr.AuthorId = tipper_wallet.remote_owner_id
    tr.CreditedUserId = tippee_wallet.remote_owner_id
    tr.CreditedWalletId = tippee_wallet.remote_id
    tr.DebitedFunds = Money_to_cents(amount)
    tr.DebitedWalletId = tipper_wallet.remote_id
    tr.Fees = Money(0, amount.currency)
    tr.Tag = str(t_id)
    execute_transfer(db, t_id, tr)
    return tr


def execute_transfer(db, t_id, tr):
    try:
        tr.save()
    except Exception as e:
        error = repr_exception(e)
        _record_transfer_result(db, t_id, 'failed', error)
        from liberapay.website import website
        website.tell_sentry(e, {}, allow_reraise=False)
        raise TransferError(error)
    return record_transfer_result(db, t_id, tr, _raise=True)


def record_transfer_result(db, t_id, tr, _raise=False):
    error = repr_error(tr)
    status = tr.Status.lower()
    assert (not error) ^ (status == 'failed')
    r = _record_transfer_result(db, t_id, status, error)
    if _raise and status == 'failed':
        raise TransferError(error)
    return r


def _record_transfer_result(db, t_id, status, error=None):
    balance = None
    with db.get_cursor() as c:
        tipper, tippee, amount, wallet_from, wallet_to, context, team = c.one("""
            UPDATE transfers
               SET status = %s
                 , error = %s
             WHERE id = %s
         RETURNING tipper, tippee, amount, wallet_from, wallet_to, context, team
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
            # Update the `tips.paid_in_advance` column
            if context in ('tip-in-advance', 'take-in-advance'):
                tip_target = team if context == 'take-in-advance' else tippee
                assert tip_target
                updated_tips = c.all("""
                    WITH latest_tip AS (
                             SELECT *
                               FROM tips
                              WHERE tipper = %(tipper)s
                                AND tippee = %(tip_target)s
                           ORDER BY mtime DESC
                              LIMIT 1
                         )
                    UPDATE tips t
                       SET paid_in_advance = (
                               coalesce_currency_amount(t.paid_in_advance, t.amount::currency) +
                               convert(%(amount)s, t.amount::currency)
                           )
                         , is_funded = true
                      FROM latest_tip lt
                     WHERE t.tipper = lt.tipper
                       AND t.tippee = lt.tippee
                       AND t.mtime >= lt.mtime
                 RETURNING t.*
                """, locals())
                assert 0 < len(updated_tips) < 10, locals()
                # Update the `takes.paid_in_advance` column
                if context == 'take-in-advance':
                    updated_takes = c.all("""
                        WITH latest_take AS (
                                 SELECT *
                                   FROM takes
                                  WHERE team = %(team)s
                                    AND member = %(tippee)s
                                    AND amount IS NOT NULL
                               ORDER BY mtime DESC
                                  LIMIT 1
                             )
                        UPDATE takes t
                           SET paid_in_advance = (
                                   coalesce_currency_amount(lt.paid_in_advance, lt.amount::currency) +
                                   convert(%(amount)s, lt.amount::currency)
                               )
                          FROM latest_take lt
                         WHERE t.team = lt.team
                           AND t.member = lt.member
                           AND t.mtime >= lt.mtime
                     RETURNING t.*
                    """, locals())
                    assert 0 < len(updated_takes) < 10, locals()
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


def refund_transfer(db, remote_id):
    tr = Transfer.get(remote_id)
    t = db.one("SELECT * FROM transfers WHERE id = %s", (tr.Tag,))
    refund_id = prepare_transfer(
        db, t.tippee, t.tipper, t.amount, 'refund', t.wallet_to, t.wallet_from,
        refund_ref=t.id
    )
    refund = TransferRefund(Transfer=tr, AuthorId=tr.AuthorId, Tag=refund_id)
    execute_transfer(db, refund_id, refund)


def refund_payin(db, exchange, amount, participant):
    """Refund a specific payin.
    """
    assert participant.id == exchange.participant

    # Record the refund attempt
    fee = vat = amount.zero()
    with db.get_cursor() as cursor:
        cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
        bundles = cursor.all("""
            SELECT b.id
              FROM cash_bundles b
             WHERE b.owner = %s
        """, (participant.id,))
        e_refund = cursor.one("""
            INSERT INTO exchanges
                        (participant, amount, fee, vat, route, status, refund_ref, wallet_id)
                 VALUES (%s, %s, %s, %s, %s, 'pre', %s, %s)
              RETURNING *
        """, (participant.id, -amount, fee, vat, exchange.route, exchange.id, exchange.wallet_id))
        cursor.run("""
            INSERT INTO exchange_events
                        (timestamp, exchange, status, wallet_delta)
                 VALUES (%s, %s, 'pre', %s)
        """, (e_refund.timestamp, e_refund.id, e_refund.amount - e_refund.fee))
        propagate_exchange(cursor, participant, e_refund, None, e_refund.amount, bundles=bundles)

    # Submit the refund
    wallet = db.one("SELECT * FROM wallets WHERE remote_id = %s", (exchange.wallet_id,))
    m_refund = PayInRefund(payin_id=exchange.remote_id)
    m_refund.AuthorId = wallet.remote_owner_id
    m_refund.Tag = str(e_refund.id)
    m_refund.DebitedFunds = Money_to_cents(amount)
    m_refund.Fees = -Money_to_cents(fee)
    try:
        m_refund.save()
    except Exception as e:
        error = repr_exception(e)
        e_refund = record_exchange_result(db, e_refund.id, '', 'failed', error, participant)
        return 'exception', e_refund
    e_refund = record_exchange_result(
        db, e_refund.id, m_refund.Id, m_refund.Status.lower(), repr_error(m_refund), participant
    )
    return e_refund.status, e_refund


def swap_currencies(db, swapper1, swapper2, amount1, amount2):
    wallet11 = swapper1.get_current_wallet(amount1.currency)
    wallet12 = swapper1.get_current_wallet(amount2.currency, create=True)
    wallet21 = swapper2.get_current_wallet(amount1.currency, create=True)
    wallet22 = swapper2.get_current_wallet(amount2.currency)
    assert wallet11.balance >= amount1, (wallet11, amount1)
    assert wallet22.balance >= amount2, (wallet22, amount2)
    t1 = prepare_transfer(
        db, swapper1.id, swapper2.id, amount1, 'swap', wallet11.remote_id, wallet21.remote_id
    )
    try:
        t2 = prepare_transfer(
            db, swapper2.id, swapper1.id, amount2, 'swap', wallet22.remote_id, wallet12.remote_id,
            counterpart=t1
        )
    except Exception:
        _record_transfer_result(db, t1, 'failed', 'canceled')
        raise
    db.run("UPDATE transfers SET counterpart = %s WHERE id = %s", (t2, t1))
    try:
        tr1 = initiate_transfer(db, t1)
    except Exception:
        _record_transfer_result(db, t2, 'failed', 'canceled')
        raise
    try:
        initiate_transfer(db, t2)
    except Exception:
        refund_transfer(db, tr1.Id)
        raise
    return t1, t2


def lock_disputed_funds(cursor, exchange, amount):
    """Prevent money that is linked to a chargeback from being withdrawn.
    """
    if amount != exchange.amount + exchange.fee:
        raise NotImplementedError("partial disputes are not implemented")
    cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
    disputed_bundles = cursor.all("""
        UPDATE cash_bundles
           SET disputed = true
         WHERE origin = %s
     RETURNING *
    """, (exchange.id,))
    disputed_bundles_sum = sum(b.amount for b in disputed_bundles)
    assert disputed_bundles_sum == exchange.amount
    original_owner = exchange.participant
    for b in disputed_bundles:
        if b.owner == original_owner:
            continue
        try_to_swap_bundle(cursor, b, original_owner)


def refund_disputed_payin(db, exchange, create_debts=False, refund_fee=False, dry_run=False):
    """Refund a specific disputed payin.
    """
    assert exchange.status == 'succeeded' and exchange.remote_id, exchange
    e_refund = db.one("SELECT e.* FROM exchanges e WHERE e.refund_ref = %s", (exchange.id,))
    if e_refund and e_refund.status == 'succeeded':
        return 'already done', e_refund

    # Lock the bundles and try to swap them
    with db.get_cursor() as cursor:
        cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
        bundles = cursor.all("""
            UPDATE cash_bundles
               SET disputed = true
             WHERE origin = %s
         RETURNING *
        """, (exchange.id,))
        bundles_sum = sum(b.amount for b in bundles)
        assert bundles_sum == exchange.amount
        original_owner = exchange.participant
        for b in bundles:
            if b.owner == original_owner:
                continue
            try_to_swap_bundle(cursor, b, original_owner)

    # Move the funds back to the original wallet
    LiberapayOrg = db.Participant.from_username('LiberapayOrg')
    assert LiberapayOrg
    return_payin_bundles_to_origin(db, exchange, LiberapayOrg, create_debts)

    # Add a debt for the fee
    if create_debts and refund_fee:
        create_debt(db, original_owner, LiberapayOrg.id, exchange.fee, exchange.id)

    # Compute and check the amount
    wallet = db.one("SELECT * FROM wallets WHERE remote_id = %s", (exchange.wallet_id,))
    if e_refund and e_refund.status == 'pre':
        amount = -e_refund.amount
    else:
        amount = min(wallet.balance, exchange.amount)
        if amount <= 0:
            return ('not enough money: wallet balance = %s' % wallet.balance), None

    # Stop here if this is a dry run
    zero = exchange.fee.zero()
    fee, vat = (exchange.fee, exchange.vat) if refund_fee else (zero, zero)
    if dry_run:
        msg = (
            '[dry run] full refund of payin #%s (liberapay id %s): amount = %s, fee = %s' %
            (exchange.remote_id, exchange.id, exchange.amount, exchange.fee)
        ) if amount + fee == exchange.amount + exchange.fee else (
            '[dry run] partial refund of payin #%s (liberapay id %s): %s of %s, fee %s of %s' %
            (exchange.remote_id, exchange.id, amount, exchange.amount, fee, exchange.fee)
        )
        return msg, None

    # Record the refund attempt
    participant = db.Participant.from_id(exchange.participant)
    if not (e_refund and e_refund.status == 'pre'):
        with db.get_cursor() as cursor:
            cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
            bundles = cursor.all("""
                SELECT id
                  FROM cash_bundles
                 WHERE origin = %s
                   AND wallet_id = %s
                   AND disputed = true
            """, (exchange.id, exchange.wallet_id))
            e_refund = cursor.one("""
                INSERT INTO exchanges
                            (participant, amount, fee, vat, route, status, refund_ref, wallet_id)
                     VALUES (%s, %s, %s, %s, %s, 'pre', %s, %s)
                  RETURNING *
            """, (participant.id, -amount, -fee, -vat, exchange.route, exchange.id, exchange.wallet_id))
            cursor.run("""
                INSERT INTO exchange_events
                            (timestamp, exchange, status, wallet_delta)
                     VALUES (%s, %s, 'pre', %s)
            """, (e_refund.timestamp, e_refund.id, e_refund.amount - e_refund.fee))
            propagate_exchange(cursor, participant, e_refund, None, e_refund.amount, bundles=bundles)

    # Submit the refund
    m_refund = PayInRefund(payin_id=exchange.remote_id)
    m_refund.AuthorId = wallet.remote_owner_id
    m_refund.Tag = str(e_refund.id)
    m_refund.DebitedFunds = Money_to_cents(amount)
    m_refund.Fees = -Money_to_cents(fee)
    try:
        m_refund.save()
    except Exception as e:
        error = repr_exception(e)
        e_refund = record_exchange_result(db, e_refund.id, '', 'failed', error, participant)
        return 'exception', e_refund
    e_refund = record_exchange_result(
        db, e_refund.id, m_refund.Id, m_refund.Status.lower(), repr_error(m_refund), participant
    )
    return e_refund.status, e_refund


def return_payin_bundles_to_origin(db, exchange, last_resort_payer, create_debts=True):
    """Transfer money linked to a specific payin back to the original owner.
    """
    currency = exchange.amount.currency
    chargebacks_account = db.Participant.get_chargebacks_account(currency)[0]
    original_owner = exchange.participant
    origin_wallet = db.one("SELECT * FROM wallets WHERE remote_id = %s", (exchange.wallet_id,))
    transfer_kw = dict(
        tippee_wallet_id=origin_wallet.remote_id,
        tippee_mango_id=origin_wallet.remote_owner_id,
    )
    payin_bundles = db.all("""
        SELECT *
          FROM cash_bundles
         WHERE origin = %s
           AND disputed = true
    """, (exchange.id,))
    grouped = group_by(payin_bundles, lambda b: (b.owner, b.withdrawal))
    for (current_owner, withdrawal), bundles in grouped.items():
        assert current_owner != chargebacks_account.id
        if current_owner == original_owner:
            continue
        amount = sum(b.amount for b in bundles)
        if current_owner is None:
            if not last_resort_payer or not create_debts:
                continue
            bundles = None
            withdrawer = db.one("SELECT participant FROM exchanges WHERE id = %s", (withdrawal,))
            payer = last_resort_payer.id
            create_debt(db, withdrawer, payer, amount, exchange.id)
            create_debt(db, original_owner, withdrawer, amount, exchange.id)
        else:
            bundles = [b.id for b in bundles]
            payer = current_owner
            if create_debts:
                create_debt(db, original_owner, payer, amount, exchange.id)
        transfer(db, payer, original_owner, amount, 'chargeback', bundles=bundles, **transfer_kw)


def recover_lost_funds(db, exchange, lost_amount, repudiation_id):
    """Recover as much money as possible from a payin which has been reverted.
    """
    original_owner = exchange.participant
    # Try (again) to swap the disputed bundles
    with db.get_cursor() as cursor:
        cursor.run("LOCK TABLE cash_bundles IN EXCLUSIVE MODE")
        disputed_bundles = cursor.all("""
            SELECT *
              FROM cash_bundles
             WHERE origin = %s
               AND disputed = true
        """, (exchange.id,))
        bundles_sum = sum(b.amount for b in disputed_bundles)
        assert bundles_sum == lost_amount - exchange.fee
        for b in disputed_bundles:
            if b.owner == original_owner:
                continue
            try_to_swap_bundle(cursor, b, original_owner)
    # Move the funds back to the original wallet
    currency = exchange.amount.currency
    chargebacks_account, credit_wallet = db.Participant.get_chargebacks_account(currency)
    LiberapayOrg = db.Participant.from_username('LiberapayOrg')
    assert LiberapayOrg
    return_payin_bundles_to_origin(db, exchange, LiberapayOrg, create_debts=True)
    # Add a debt for the fee
    create_debt(db, original_owner, LiberapayOrg.id, exchange.fee, exchange.id)
    # Send the funds to the credit wallet
    # We have to do a SettlementTransfer instead of a normal Transfer. The amount
    # can't exceed the original payin amount, so we can't settle the fee debt.
    original_owner = db.Participant.from_id(original_owner)
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
    tr.DebitedFunds = Money_to_cents(exchange.amount)
    tr.DebitedWalletId = from_wallet
    tr.Fees = Money(0, currency)
    tr.RepudiationId = repudiation_id
    tr.Tag = str(t_id)
    return execute_transfer(db, t_id, tr)


def try_to_swap_bundle(cursor, b, original_owner):
    """Attempt to switch a disputed cash bundle with a "safe" one.
    """
    currency = b.amount.currency
    swappable_origin_bundles = cursor.all("""
        SELECT *
          FROM cash_bundles
         WHERE owner = %s
           AND disputed IS NOT TRUE
           AND locked_for IS NULL
           AND amount::currency = %s
      ORDER BY ts ASC
    """, (original_owner, currency))
    try_to_swap_bundle_with(cursor, b, swappable_origin_bundles)
    merge_cash_bundles(cursor, original_owner)
    if b.withdrawal:
        withdrawer = cursor.one(
            "SELECT participant FROM exchanges WHERE id = %s", (b.withdrawal,)
        )
        swappable_recipient_bundles = cursor.all("""
            SELECT *
              FROM cash_bundles
             WHERE owner = %s
               AND disputed IS NOT TRUE
               AND locked_for IS NULL
               AND amount::currency = %s
          ORDER BY ts ASC, amount = %s DESC
        """, (withdrawer, currency, b.amount))
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
    return cursor.one("""
        INSERT INTO cash_bundles
                    (owner, origin, amount, ts, withdrawal, disputed, wallet_id)
             VALUES (%s, %s, %s, %s, %s, %s, %s)
          RETURNING *;
    """, (b.owner, b.origin, amount, b.ts, b.withdrawal, b.disputed, b.wallet_id))


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
    print("Syncing with Mangopay...")
    check_db(db)

    exchanges = db.all("""
        SELECT *, (e.timestamp < current_timestamp - interval '1 day') AS is_old
          FROM exchanges e
         WHERE e.status = 'pre'
    """)
    for e in exchanges:
        p = db.Participant.from_id(e.participant)
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
        tipper = db.Participant.from_id(t.tipper)
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
    from liberapay.billing.payday import Payday
    from liberapay.website import website
    wallets = website.db.all("""
        SELECT *
          FROM wallets
         WHERE NOT remote_id LIKE 'CREDIT_%'
    """)
    for w in wallets:
        check_wallet_balance(w)
        sleep(max(getattr(Payday, 'transfer_delay', 0), 0.1))
