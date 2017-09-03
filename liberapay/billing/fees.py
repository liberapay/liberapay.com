"""Functions to compute transaction fees.
"""
from __future__ import division, print_function, unicode_literals

from decimal import Decimal, ROUND_UP

from pando.utils import typecheck

from liberapay.constants import (
    D_CENT,
    PAYIN_CARD_MIN, FEE_PAYIN_CARD,
    FEE_PAYIN_BANK_WIRE, PAYIN_BANK_WIRE_MIN,
    FEE_PAYIN_DIRECT_DEBIT, PAYIN_DIRECT_DEBIT_MIN,
    FEE_PAYOUT, FEE_PAYOUT_OUTSIDE_SEPA, SEPA,
    FEE_VAT,
)


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


upcharge_bank_wire = lambda amount: upcharge(amount, FEE_PAYIN_BANK_WIRE, PAYIN_BANK_WIRE_MIN)
upcharge_card = lambda amount: upcharge(amount, FEE_PAYIN_CARD, PAYIN_CARD_MIN)
upcharge_direct_debit = lambda amount: upcharge(amount, FEE_PAYIN_DIRECT_DEBIT, PAYIN_DIRECT_DEBIT_MIN)


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
    typecheck(amount, Decimal)
    country = get_bank_account_country(ba)
    if country in SEPA:
        fee = FEE_PAYOUT
    else:
        fee = FEE_PAYOUT_OUTSIDE_SEPA
    return skim_amount(amount, fee)
