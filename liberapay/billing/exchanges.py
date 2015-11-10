"""Functions for moving money between Liberapay and the outside world.
"""
from __future__ import division, print_function, unicode_literals

from decimal import Decimal, ROUND_UP

from aspen import Response
from aspen.utils import typecheck
from mangopaysdk.entities.payin import PayIn
from mangopaysdk.entities.payout import PayOut
from mangopaysdk.entities.transfer import Transfer
from mangopaysdk.entities.wallet import Wallet
from mangopaysdk.types.exceptions.responseexception import ResponseException
from mangopaysdk.types.money import Money

from liberapay.billing import mangoapi, PayInExecutionDetailsDirect, PayInPaymentDetailsCard, PayOutPaymentDetailsBankWire
from liberapay.constants import QUARANTINE
from liberapay.exceptions import (
    LazyResponse, NegativeBalance, NotEnoughWithdrawableMoney,
    TransactionFeeTooHigh, UserIsSuspicious
)
from liberapay.models import check_db
from liberapay.models.participant import Participant
from liberapay.models.exchange_route import ExchangeRoute


MINIMUM_CHARGE = Decimal("10.00")

# https://www.mangopay.com/pricing/
FEE_CHARGE = (Decimal("0.18"), Decimal("0.018"))  # 0.18 euros + 1.8%
FEE_CREDIT = 0
FEE_CREDIT_OUTSIDE_SEPA = Decimal("2.5")

SEPA_ZONE = set("""
    AT BE BG CH CY CZ DE DK EE ES ES FI FR GB GI GR HR HU IE IS IT LI LT LU LV
    MC MT NL NO PL PT RO SE SI SK
""".split())

QUARANTINE = '%s days' % QUARANTINE.days


def upcharge(amount):
    """Given an amount, return a higher amount and the difference.
    """
    typecheck(amount, Decimal)

    if amount < MINIMUM_CHARGE:
        amount = MINIMUM_CHARGE

    # a = c - vf * c - ff  =>  c = (a + ff) / (1 - vf)
    # a = amount ; c = charge amount ; ff = fixed fee ; vf = variable fee
    charge_amount = (amount + FEE_CHARGE[0]) / (1 - FEE_CHARGE[1])
    charge_amount = charge_amount.quantize(FEE_CHARGE[0], rounding=ROUND_UP)
    fee = charge_amount - amount

    return charge_amount, fee

assert upcharge(MINIMUM_CHARGE) == (Decimal('10.37'), Decimal('0.37')), upcharge(MINIMUM_CHARGE)


def skim_credit(amount, ba):
    """Given an amount, return a lower amount and the difference.

    The returned amount can be negative, look out for that.
    """
    typecheck(amount, Decimal)
    if ba.Type == 'IBAN':
        country = ba.Details.IBAN[:2].upper()
    elif ba.Type in ('US', 'GB', 'CA'):
        country = ba.Type
    else:
        assert ba.Type == 'OTHER', ba.Type
        country = ba.Details.Country.upper()
    if country in SEPA_ZONE:
        fee = FEE_CREDIT
    else:
        fee = FEE_CREDIT_OUTSIDE_SEPA
    return amount - fee, fee


def repr_error(o):
    r = o.ResultCode
    if r == '000000':
        return
    msg = getattr(o, 'ResultMessage', None)
    if msg:
        r += ': ' + msg
    return r


def repr_exception(e):
    if isinstance(e, ResponseException):
        return '%s %s' % (e.Code, e.Message)
    else:
        return repr(e)


def create_wallet(db, participant):
    w = Wallet()
    w.Owners.append(participant.mangopay_user_id)
    w.Description = str(participant.id)
    w.Currency = 'EUR'
    w = mangoapi.wallets.Create(w)
    db.run("""
        UPDATE participants
           SET mangopay_wallet_id = %s
         WHERE id = %s
    """, (w.Id, participant.id))
    participant.set_attributes(mangopay_wallet_id=w.Id)
    return w.Id


def test_hook():
    return


def payout(db, participant, amount):
    if participant.is_suspicious:
        raise UserIsSuspicious

    route = ExchangeRoute.from_network(participant, 'mango-ba')
    assert route
    ba = mangoapi.users.GetBankAccount(participant.mangopay_user_id, route.address)

    # Do final calculations
    credit_amount, fee = skim_credit(amount, ba)
    if credit_amount <= 0 or fee / credit_amount > 0.1:
        raise TransactionFeeTooHigh

    # Try to dance with MangoPay
    e_id = record_exchange(db, route, -credit_amount, fee, participant, 'pre')
    payout = PayOut()
    payout.AuthorId = participant.mangopay_user_id
    payout.DebitedFunds = Money(int(credit_amount * 100), 'EUR')
    payout.DebitedWalletId = participant.mangopay_wallet_id
    payout.Fees = Money(int(fee * 100), 'EUR')
    payout.MeanOfPaymentDetails = PayOutPaymentDetailsBankWire(
        BankAccountId=route.address,
        BankWireRef=str(e_id),
    )
    payout.Tag = str(e_id)
    try:
        test_hook()
        mangoapi.payOuts.Create(payout)
        return record_exchange_result(db, e_id, 'created', None, participant)
    except Exception as e:
        error = repr_exception(e)
        return record_exchange_result(db, e_id, 'failed', error, participant)


def charge(db, participant, amount, return_url):
    """Charge the participant's credit card.

    Amount should be the nominal amount. We'll compute fees below this function
    and add it to amount to end up with charge_amount.

    """
    typecheck(amount, Decimal)

    if participant.is_suspicious:
        raise UserIsSuspicious

    route = ExchangeRoute.from_network(participant, 'mango-cc')
    assert route

    charge_amount, fee = upcharge(amount)
    amount = charge_amount - fee

    e_id = record_exchange(db, route, amount, fee, participant, 'pre')
    payin = PayIn()
    payin.AuthorId = participant.mangopay_user_id
    if not participant.mangopay_wallet_id:
        create_wallet(db, participant)
    payin.CreditedWalletId = participant.mangopay_wallet_id
    payin.DebitedFunds = Money(int(charge_amount * 100), 'EUR')
    payin.ExecutionDetails = PayInExecutionDetailsDirect(
        CardId=route.address,
        SecureModeReturnURL=return_url,
    )
    payin.Fees = Money(int(fee * 100), 'EUR')
    payin.PaymentDetails = PayInPaymentDetailsCard(CardType='CB_VISA_MASTERCARD')
    payin.Tag = str(e_id)
    try:
        test_hook()
        payin = mangoapi.payIns.Create(payin)
    except Exception as e:
        error = repr_exception(e)
        return record_exchange_result(db, e_id, 'failed', error, participant)

    if payin.ExecutionDetails.SecureModeRedirectURL:
        raise Response(302, headers={'Location': payin.ExecutionDetails.SecureModeRedirectURL})

    return record_exchange_result(db, e_id, 'succeeded', None, participant)


def record_exchange(db, route, amount, fee, participant, status, error=None):
    """Given a Bunch of Stuff, return an int (exchange_id).

    Records in the exchanges table have these characteristics:

        amount  It's negative for credits (representing an outflow from
                Liberapay to you) and positive for charges.
                The sign is how we differentiate the two in, e.g., the
                history page.

        fee     The payment processor's fee. It's always positive.

    """

    with db.get_cursor() as cursor:

        e = cursor.one("""
            INSERT INTO exchanges
                   (amount, fee, participant, status, route, note)
            VALUES (%s, %s, %s, %s, %s, %s)
         RETURNING *
        """, (amount, fee, participant.id, status, route.id, error))

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
         RETURNING id, amount, fee, participant, recorder, note, status, timestamp
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
            amount = -amount + e.fee if status == 'failed' else 0
        else:
            amount = amount if status == 'succeeded' else 0
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
            SELECT *
              FROM cash_bundles
             WHERE owner = %s
               AND ts < now() - INTERVAL %s
          ORDER BY ts
        """, (participant.id, QUARANTINE))
        withdrawable = sum(b.amount for b in bundles)
        x = -amount
        if x > withdrawable:
            raise NotEnoughWithdrawableMoney(Money(withdrawable, 'EUR'))
        for b in bundles:
            if x >= b.amount:
                cursor.run("DELETE FROM cash_bundles WHERE id = %s", (b.id,))
                x -= b.amount
                if x == 0:
                    break
            else:
                assert x > 0
                cursor.run("""
                    UPDATE cash_bundles
                       SET amount = (amount - %s)
                     WHERE id = %s
                """, (x, b.id))
                break
    elif amount > 0:
        cursor.run("""
            INSERT INTO cash_bundles
                        (owner, origin, amount, ts)
                 VALUES (%s, %s, %s, %s)
        """, (participant.id, exchange.id, amount, exchange.timestamp))

    participant.set_attributes(balance=new_balance)

    if amount != 0:
        participant.update_giving_and_tippees(cursor)


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
    tr.CreditedWalletID = kw.get('tippee_wallet_id') or get(tippee, 'mangopay_wallet_id')
    if not tr.CreditedWalletID:
        tr.CreditedWalletID = create_wallet(db, Participant.from_id(tippee))
    tr.DebitedFunds = Money(int(amount * 100), 'EUR')
    tr.DebitedWalletID = kw.get('tipper_wallet_id') or get(tipper, 'mangopay_wallet_id')
    tr.Fees = Money(0, 'EUR')
    tr.Tag = str(t_id)
    tr = mangoapi.transfers.Create(tr)
    return record_transfer_result(db, t_id, tr)


def record_transfer_result(db, t_id, tr):
    error = repr_error(tr)
    status = tr.Status.lower()
    assert (not error) ^ (status == 'failed')
    return _record_transfer_result(db, t_id, status)


def _record_transfer_result(db, t_id, status):
    with db.get_cursor() as c:
        tipper, tippee, amount = c.one("""
            UPDATE transfers
               SET status = %s
             WHERE id = %s
         RETURNING tipper, tippee, amount
        """, (status, t_id))
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
                SELECT *
                  FROM cash_bundles
                 WHERE owner = %s
              ORDER BY ts
            """, (tipper,))
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
            return balance
    raise LazyResponse(500, lambda _: _("Transfering the money failed, please try again."))


def sync_with_mangopay(db):
    """We can get out of sync with MangoPay if record_exchange_result wasn't
    completed. This is where we fix that.
    """
    check_db(db)

    exchanges = db.all("SELECT * FROM exchanges WHERE status = 'pre'")
    for e in exchanges:
        p = Participant.from_id(e.participant)
        transactions = mangoapi.users.GetTransactions(p.mangopay_user_id)
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
        transactions = mangoapi.wallets.GetTransactions(tipper.mangopay_wallet_id)
        transactions = [x for x in transactions if x.Type == 'TRANSFER' and x.Tag == str(t.id)]
        assert len(transactions) < 2
        if transactions:
            record_transfer_result(db, t.id, transactions[0])
        else:
            # The transfer didn't happen, remove it
            db.run("DELETE FROM transfers WHERE id = %s", (t.id,))

    check_db(db)
