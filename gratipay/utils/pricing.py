from decimal import Decimal as D, ROUND_HALF_EVEN


def suggested_payment(usage):
    if usage >= 500:
        percentage = D('0.02')
    elif usage >= 20:
        percentage = D('0.05')
    else:
        percentage = D('0.10')

    suggestion = usage * percentage
    if suggestion == 0:
        rounded = suggestion
    elif suggestion < 0.25:
        rounded = D('0.25')
    elif suggestion < 0.50:
        rounded = D('0.50')
    elif suggestion < 1:
        rounded = D('1.00')
    else:
        rounded = suggestion.quantize(D('0'), ROUND_HALF_EVEN)

    return rounded


def suggested_payment_low_high(usage):
    # Above $500/wk we suggest 2%.
    if usage >= 5000:
        low = D('100.00')
        high = D('1000.00')
    elif usage >= 500:
        low = D('10.00')
        high = D('100.00')

    # From $20 to $499 we suggest 5%.
    elif usage >= 100:
        low = D('5.00')
        high = D('25.00')
    elif usage >= 20:
        low = D('1.00')
        high = D('5.00')

    # Below $20 we suggest 10%.
    elif usage >= 5:
        low = D('0.50')
        high = D('2.00')
    else:
        low = D('0.10')
        high = D('1.00')

    return {'cta_low': low, 'cta_high': high}
