"""Functions for moving money between Liberapay and the outside world.
"""
from __future__ import division, print_function, unicode_literals

from decimal import Decimal, ROUND_UP

from mangopay.exceptions import APIError
from mangopay.resources import (
    BankAccount, BankWirePayIn, BankWirePayOut, DirectPayIn, Transaction,
    Transfer, Wallet,
)
from mangopay.utils import Money
from pando.utils import typecheck

from liberapay.constants import (
    D_CENT, D_ZERO,
    PAYIN_CARD_MIN, FEE_PAYIN_CARD,
    FEE_PAYIN_BANK_WIRE,
    FEE_PAYOUT, FEE_PAYOUT_OUTSIDE_SEPA, FEE_PAYOUT_WARN, QUARANTINE, SEPA_ZONE,
    FEE_VAT,
)
from liberapay.exceptions import (
    NegativeBalance, NotEnoughWithdrawableMoney, PaydayIsRunning,
    FeeExceedsAmount, TransactionFeeTooHigh, TransferError,
    AccountSuspended, Redirect,
)
from liberapay.models import check_db
from liberapay.models.participant import Participant
from liberapay.models.exchange_route import ExchangeRoute


Money.__eq__ = lambda a, b: isinstance(b, Money) and a.__dict__ == b.__dict__
Money.__repr__ = lambda m: '<Money Amount=%(amount)r Currency=%(currency)r>' % m.__dict__


QUARANTINE = '%s days' % QUARANTINE.days


def upcharge(amount, fees, min_amount):
    """Given an amount, return a higher amount and the difference.
    """
    typecheck(amount, Decimal)

    if amount < min_amount:
        amount = min_amount

    # a = c - vf * c - ff  =>  c = (a + ff) / (1 - vf)
    # a = amount ; c = charge amount ; ff = fixed fee ; vf = variable fee
    charge_amount = (amount + fees.fix) / (1 - fees.var)
    fee = charge_amount - amount

    # + VAT
    vat = fee * FEE_VAT
    charge_amount += vat
    fee += vat

    # Round
    charge_amount = charge_amount.quantize(D_CENT, rounding=ROUND_UP)
    fee = fee.quantize(D_CENT, rounding=ROUND_UP)
    vat = vat.quantize(D_CENT, rounding=ROUND_UP)

    return charge_amount, fee, vat


upcharge_bank_wire = lambda amount: upcharge(amount, FEE_PAYIN_BANK_WIRE, D_ZERO)
upcharge_card = lambda amount: upcharge(amount, FEE_PAYIN_CARD, PAYIN_CARD_MIN)


def skim_amount(amount, fees):
    """Given a nominal amount, compute the fees, taxes, and the actual amount.
    """
    fee = amount * fees.var + fees.fix
    vat = fee * FEE_VAT
    fee += vat
    fee = fee.quantize(D_CENT, rounding=ROUND_UP)
    vat = vat.quantize(D_CENT, rounding=ROUND_UP)
    return amount - fee, fee, vat


skim_bank_wire = lambda amount: skim_amount(amount, FEE_PAYIN_BANK_WIRE)


def skim_credit(amount, ba):
    """Given a payout amount, return a lower amount, the fee, and taxes.

    The returned amount can be negative, look out for that.
    """
    typecheck(amount, Decimal)
    if ba.Type == 'IBAN':
        country = ba.IBAN[:2].upper()
    elif ba.Type in ('US', 'GB', 'CA'):
        country = ba.Type
    else:
        assert ba.Type == 'OTHER', ba.Type
        country = ba.Country.upper()
    if country in SEPA_ZONE:
        fee = FEE_PAYOUT
    else:
        fee = FEE_PAYOUT_OUTSIDE_SEPA
    return skim_amount(amount, fee)


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


def payout(db, participant, amount, ignore_high_fee=False):
    assert amount > 0

    if participant.is_suspended:
        raise AccountSuspended()

    payday = db.one("SELECT * FROM paydays WHERE ts_start > ts_end")
    if payday:
        raise PaydayIsRunning

    route = ExchangeRoute.from_network(participant, 'mango-ba')
    assert route
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


def charge(db, participant, amount, return_url):
    """Charge the participant's credit card.

    Amount should be the nominal amount. We'll compute fees below this function
    and add it to amount to end up with charge_amount.

    """
    typecheck(amount, Decimal)

    route = ExchangeRoute.from_network(participant, 'mango-cc')
    assert route

    charge_amount, fee, vat = upcharge_card(amount)
    amount = charge_amount - fee

    e_id = record_exchange(db, route, amount, fee, vat, participant, 'pre')
    payin = DirectPayIn()
    payin.AuthorId = participant.mangopay_user_id
    if not participant.mangopay_wallet_id:
        create_wallet(db, participant)
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

    e_id = record_exchange(db, route, amount, fee, vat, participant, 'pre')
    payin = BankWirePayIn()
    payin.AuthorId = participant.mangopay_user_id
    if not participant.mangopay_wallet_id:
        create_wallet(db, participant)
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
    return db.one("""
        INSERT INTO exchanges
               (amount, fee, vat, participant, status, route, note, refund_ref)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
     RETURNING id
    """, (amount, fee, vat, participant.id, 'created', route.id, None, e_origin.id))


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

        e = cursor.one("""
            INSERT INTO exchanges
                   (amount, fee, vat, participant, status, route, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
         RETURNING *
        """, (amount, fee, vat, participant.id, status, route.id, error))

        if status == 'failed':
            propagate_exchange(cursor, participant, e, route, error, 0)
        elif amount < 0:
            amount -= fee
            propagate_exchange(cursor, participant, e, route, '', amount)

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
         RETURNING id, amount, fee, vat, participant, recorder, note, status, timestamp
                 , ( SELECT r.*::exchange_routes
                       FROM exchange_routes r
                      WHERE r.id = e.route
                   ) AS route
        """, locals())
        if not e:
            return
        assert participant.id == e.participant
        assert isinstance(e.route, ExchangeRoute)

        amount = e.amount
        if amount < 0:
            amount = -amount + max(e.fee, 0) if status == 'failed' else 0
        else:
            amount = amount - min(e.fee, 0) if status == 'succeeded' else 0
        propagate_exchange(cursor, participant, e, e.route, error, amount)

        return e


def propagate_exchange(cursor, participant, exchange, route, error, amount):
    """Propagates an exchange's result to the participant's balance and the
    route's status.
    """
    route.update_error(error or '')

    new_balance = cursor.one("""
        UPDATE participants
           SET balance=(balance + %s)
         WHERE id=%s
     RETURNING balance
    """, (amount, participant.id))

    if amount < 0 and new_balance < 0:
        raise NegativeBalance

    if amount < 0:
        bundles = cursor.all("""
            LOCK TABLE cash_bundles IN EXCLUSIVE MODE;
            SELECT b.*
              FROM cash_bundles b
              JOIN exchanges e ON e.id = b.origin
             WHERE b.owner = %s
               AND b.ts < now() - INTERVAL %s
          ORDER BY b.owner = e.participant DESC, b.ts
        """, (participant.id, QUARANTINE))
        withdrawable = sum(b.amount for b in bundles)
        x = -amount
        if x > withdrawable:
            raise NotEnoughWithdrawableMoney(Money(withdrawable, 'EUR'))
        for b in bundles:
            if x >= b.amount:
                cursor.run("""
                    INSERT INTO e2e_transfers
                                (origin, withdrawal, amount)
                         VALUES (%s, %s, %s)
                """, (b.origin, exchange.id, b.amount))
                cursor.run("DELETE FROM cash_bundles WHERE id = %s", (b.id,))
                x -= b.amount
                if x == 0:
                    break
            else:
                assert x > 0
                cursor.run("""
                    INSERT INTO e2e_transfers
                                (origin, withdrawal, amount)
                         VALUES (%s, %s, %s)
                """, (b.origin, exchange.id, x))
                cursor.run("""
                    UPDATE cash_bundles
                       SET amount = (amount - %s)
                     WHERE id = %s
                """, (x, b.id))
                break
    elif amount > 0 and exchange.amount < 0:
        cursor.run("""
            LOCK TABLE cash_bundles IN EXCLUSIVE MODE;
            INSERT INTO cash_bundles
                        (owner, origin, amount, ts)
                 SELECT %(p_id)s, t.origin, t.amount, e.timestamp
                   FROM e2e_transfers t
                   JOIN exchanges e ON e.id = t.origin
                  WHERE t.withdrawal = %(e_id)s;
            DELETE FROM e2e_transfers WHERE withdrawal = %(e_id)s;
        """, dict(p_id=participant.id, e_id=exchange.id))
    elif amount > 0:
        cursor.run("""
            INSERT INTO cash_bundles
                        (owner, origin, amount, ts)
                 VALUES (%s, %s, %s, %s)
        """, (participant.id, exchange.id, amount, exchange.timestamp))

    participant.set_attributes(balance=new_balance)

    if amount != 0:
        participant.update_giving_and_tippees(cursor)
        merge_cash_bundles(cursor, participant.id)


def transfer(db, tipper, tippee, amount, context, **kw):
    t_id = db.one("""
        INSERT INTO transfers
                    (tipper, tippee, amount, context, team, status)
             VALUES (%s, %s, %s, %s, %s, 'pre')
          RETURNING id
    """, (tipper, tippee, amount, context, kw.get('team')))
    get = lambda id, col: db.one("SELECT {0} FROM participants WHERE id = %s".format(col), (id,))
    tr = Transfer()
    tr.AuthorId = kw.get('tipper_mango_id') or get(tipper, 'mangopay_user_id')
    tr.CreditedUserId = kw.get('tippee_mango_id') or get(tippee, 'mangopay_user_id')
    tr.CreditedWalletId = kw.get('tippee_wallet_id') or get(tippee, 'mangopay_wallet_id')
    if not tr.CreditedWalletId:
        tr.CreditedWalletId = create_wallet(db, Participant.from_id(tippee))
    tr.DebitedFunds = Money(int(amount * 100), 'EUR')
    tr.DebitedWalletId = kw.get('tipper_wallet_id') or get(tipper, 'mangopay_wallet_id')
    tr.Fees = Money(0, 'EUR')
    tr.Tag = str(t_id)
    tr.save()
    return record_transfer_result(db, t_id, tr)


def record_transfer_result(db, t_id, tr):
    error = repr_error(tr)
    status = tr.Status.lower()
    assert (not error) ^ (status == 'failed')
    return _record_transfer_result(db, t_id, status, error)


def _record_transfer_result(db, t_id, status, error=None):
    balance = None
    with db.get_cursor() as c:
        tipper, tippee, amount = c.one("""
            UPDATE transfers
               SET status = %s
                 , error = %s
             WHERE id = %s
         RETURNING tipper, tippee, amount
        """, (status, error, t_id))
        if status == 'succeeded':
            balance = c.one("""

                UPDATE participants
                   SET balance = balance + %(amount)s
                 WHERE id = %(tippee)s;

                UPDATE participants
                   SET balance = balance - %(amount)s
                 WHERE id = %(tipper)s
                   AND balance - %(amount)s >= 0
             RETURNING balance;

            """, locals())
            if balance is None:
                raise NegativeBalance
            bundles = c.all("""
                LOCK TABLE cash_bundles IN EXCLUSIVE MODE;
                SELECT b.*
                  FROM cash_bundles b
                  JOIN exchanges e ON e.id = b.origin
                 WHERE b.owner = %s
              ORDER BY e.participant = %s DESC, b.ts
            """, (tipper, tippee))
            x = amount
            for b in bundles:
                if x >= b.amount:
                    c.run("""
                        UPDATE cash_bundles
                           SET owner = %s
                         WHERE id = %s
                    """, (tippee, b.id))
                    x -= b.amount
                    if x == 0:
                        break
                else:
                    c.run("""
                        UPDATE cash_bundles
                           SET amount = (amount - %s)
                         WHERE id = %s;

                        INSERT INTO cash_bundles
                                    (owner, origin, amount, ts)
                             VALUES (%s, %s, %s, %s);
                    """, (x, b.id, tippee, b.origin, x, b.ts))
                    break
    if balance is not None:
        merge_cash_bundles(db, tippee)
        return balance
    raise TransferError(error)


def merge_cash_bundles(db, p_id):
    return db.one("""
        LOCK TABLE cash_bundles IN EXCLUSIVE MODE;
        WITH regroup AS (
                 SELECT owner, origin, sum(amount) AS amount, max(ts) AS ts
                   FROM cash_bundles
                  WHERE owner = %s
               GROUP BY owner, origin
                 HAVING count(*) > 1
             ),
             inserted AS (
                 INSERT INTO cash_bundles
                             (owner, origin, amount, ts)
                      SELECT owner, origin, amount, ts
                        FROM regroup
                   RETURNING *
             ),
             deleted AS (
                 DELETE
                   FROM cash_bundles b
                  USING regroup g
                  WHERE b.owner = g.owner
                    AND b.origin = g.origin
              RETURNING b.*
             )
        SELECT (SELECT json_agg(d) FROM deleted d) AS before
             , (SELECT json_agg(i) FROM inserted i) AS after
    """, (p_id,))


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
            db.run("DELETE FROM transfers WHERE id = %s", (t.id,))

    check_db(db)
