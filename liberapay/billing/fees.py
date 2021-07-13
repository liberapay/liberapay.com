"""Functions to compute transaction fees.
"""

from mangopay.utils import Money

from liberapay.constants import FEE_PAYOUT, Fees


def skim_amount(amount, fees):
    """Given a nominal amount, compute the fees, taxes, and the actual amount.
    """
    fee = amount * fees.var + fees.fix
    vat = fee * Fees.VAT
    fee += vat
    fee = fee.round_up()
    vat = vat.round_up()
    return amount - fee, fee, vat


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
