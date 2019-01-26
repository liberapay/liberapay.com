"""Functions to compute transaction fees.
"""

from mangopay.utils import Money

from liberapay.constants import (
    PAYIN_CARD_MIN, FEE_PAYIN_CARD,
    FEE_PAYIN_BANK_WIRE, PAYIN_BANK_WIRE_MIN,
    FEE_PAYIN_DIRECT_DEBIT, PAYIN_DIRECT_DEBIT_MIN,
    FEE_PAYOUT,
    Fees,
)


def upcharge(amount, fees, min_amounts):
    """Given an amount, return a higher amount and the difference.
    """
    assert isinstance(amount, Money), type(amount)

    fees = fees if isinstance(fees, Fees) else fees[amount.currency]

    min_amount = min_amounts[amount.currency]
    if amount < min_amount:
        amount = min_amount

    # a = c - vf * c - ff  =>  c = (a + ff) / (1 - vf)
    # a = amount ; c = charge amount ; ff = fixed fee ; vf = variable fee
    charge_amount = (amount + fees.fix) / (1 - fees.var)
    fee = charge_amount - amount

    # + VAT
    vat = fee * Fees.VAT
    charge_amount += vat
    fee += vat

    # Round
    charge_amount = charge_amount.round_up()
    fee = fee.round_up()
    vat = vat.round_up()

    return charge_amount, fee, vat


upcharge_bank_wire = lambda amount: upcharge(amount, FEE_PAYIN_BANK_WIRE, PAYIN_BANK_WIRE_MIN)
upcharge_card = lambda amount: upcharge(amount, FEE_PAYIN_CARD, PAYIN_CARD_MIN)
upcharge_direct_debit = lambda amount: upcharge(amount, FEE_PAYIN_DIRECT_DEBIT, PAYIN_DIRECT_DEBIT_MIN)


def skim_amount(amount, fees):
    """Given a nominal amount, compute the fees, taxes, and the actual amount.
    """
    fee = amount * fees.var + fees.fix
    vat = fee * Fees.VAT
    fee += vat
    fee = fee.round_up()
    vat = vat.round_up()
    return amount - fee, fee, vat


skim_bank_wire = lambda amount: skim_amount(amount, FEE_PAYIN_BANK_WIRE)


def get_bank_account_country(ba):
    if ba.Type == 'IBAN':
        return ba.IBAN[:2].upper()
    elif ba.Type in ('US', 'GB', 'CA'):
        return ba.Type
    else:
        assert ba.Type == 'OTHER', ba.Type
        return ba.Country.upper()


def skim_credit(amount, ba):
    """Given a payout amount, return a lower amount, the fee, and taxes.

    The returned amount can be negative, look out for that.
    """
    assert isinstance(amount, Money), type(amount)
    fees = FEE_PAYOUT[amount.currency]
    country = get_bank_account_country(ba)
    if 'domestic' in fees:
        countries, domestic_fee = fees['domestic']
        if country in countries:
            fee = domestic_fee
        else:
            fee = fees['foreign']
    else:
        fee = fees['*']
    return skim_amount(amount, fee)
