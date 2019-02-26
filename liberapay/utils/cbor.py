from datetime import date, timedelta
from decimal import Decimal

import cbor2

from ..i18n.currencies import Money, MoneyBasket


CBORTag = cbor2.encoder.CBORTag
encode_semantic = cbor2.encoder.encode_semantic


# Dates
# =====
# Upstream issue: https://github.com/agronholm/cbor2/issues/37
# Spec: https://j-richter.github.io/CBOR/date.html

EPOCH = date(1970, 1, 1)


def encode_date(encoder, value):
    encode_semantic(encoder, CBORTag(100, value.isoformat()))


def decode_date(decoder, value, shareable_index=None):
    if type(value) == str:
        return date(*map(int, value.split('-')))
    elif type(value) == int:
        return EPOCH + timedelta(days=value)
    else:
        raise TypeError("expected str or int, got %r" % type(value))


cbor2.encoder.default_encoders[date] = encode_date
cbor2.decoder.semantic_decoders[100] = decode_date


# Money and MoneyBasket
# =====================
# Spec: https://liberapay.github.io/specs/cbor-money.html

def encode_Money(encoder, value):
    if set(value.__dict__.keys()) == {'amount', 'currency'}:
        encode_semantic(encoder, CBORTag(77111, '%s%s' % (value.currency, value.amount)))
    else:
        attrs = {
            k: v for k, v in value.__dict__.items()
            if k not in {'amount', 'currency'}
        }
        encode_semantic(encoder, CBORTag(77111, [value.currency, value.amount, attrs]))


def decode_Money(decoder, value, shareable_index=None):
    if type(value) is list:
        r = Money(amount=value[1], currency=value[0])
        if len(value) > 2:
            r.__dict__.update(value[2])
            if len(value) > 3:
                raise ValueError("the array is longer than expected (%i > 3)" % len(value))
    elif type(value) is str:
        r = Money(value[3:], value[:3])
    else:
        raise TypeError("expected list or str, got %r" % type(value))
    return r


def encode_MoneyBasket(encoder, value):
    amounts = {k: v for k, v in value.amounts.items() if v}
    if value.__dict__:
        attrs = value.__dict__
        encode_semantic(encoder, CBORTag(77112, dict(amounts, attrs=attrs)))
    else:
        encode_semantic(encoder, CBORTag(77112, amounts))


def decode_MoneyBasket(decoder, value, shareable_index=None):
    r = MoneyBasket()
    r.__dict__.update(value.pop('attrs', ()))
    for k, v in value.items():
        if len(k) == 3 and k.isupper():
            r.amounts[k] = Decimal(v)
        else:
            raise ValueError("key %r is not a currency code" % k)
    return r


cbor2.encoder.default_encoders[Money] = encode_Money
cbor2.encoder.default_encoders[MoneyBasket] = encode_MoneyBasket

cbor2.decoder.semantic_decoders[77111] = decode_Money
cbor2.decoder.semantic_decoders[77112] = decode_MoneyBasket


dumps = cbor2.dumps
loads = cbor2.loads
