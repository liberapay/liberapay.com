from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

import cbor2
from markupsafe import Markup

from ..i18n.currencies import Money, MoneyBasket
from .types import Object


CBORDecoder = cbor2.decoder.CBORDecoder
CBORTag = cbor2.encoder.CBORTag

default_encoders = cbor2.encoder.default_encoders.copy()
semantic_decoders = {}


# Dates
# =====
# Upstream issue: https://github.com/agronholm/cbor2/issues/85
# Spec: https://datatracker.ietf.org/doc/html/rfc8943

EPOCH = date(1970, 1, 1)


def encode_date(encoder, value):
    encoder.encode_semantic(CBORTag(100, (value - EPOCH).days))


def decode_date(decoder, value, shareable_index=None):
    if type(value) is str:
        # We used to encode dates as strings. The original spec allowed it.
        return date(*map(int, value.split('-')))
    elif type(value) is int:
        return EPOCH + timedelta(days=value)
    else:
        raise TypeError("expected str or int, got %r" % type(value))


default_encoders[date] = encode_date
semantic_decoders[100] = decode_date


# Markup
# ======

def encode_Markup(encoder, value):
    raise NotImplementedError()

default_encoders[Markup] = encode_Markup


# Money and MoneyBasket
# =====================
# Spec: https://liberapay.github.io/specs/cbor-money.html

def encode_Money(encoder, value):
    if value.fuzzy:
        attrs = {'fuzzy': True}
        encoder.encode_semantic(CBORTag(77111, [value.currency, value.amount, attrs]))
    else:
        encoder.encode_semantic(CBORTag(77111, '%s%s' % (value.currency, value.amount)))


def decode_Money(decoder, value, shareable_index=None):
    if type(value) is list:
        r = Money(amount=value[1], currency=value[0])
        if len(value) > 2:
            for k, v in value[2].items():
                setattr(r, k, v)
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
        encoder.encode_semantic(CBORTag(77112, dict(amounts, attrs=attrs)))
    else:
        encoder.encode_semantic(CBORTag(77112, amounts))


def decode_MoneyBasket(decoder, value, shareable_index=None):
    r = MoneyBasket()
    r.__dict__.update(value.pop('attrs', ()))
    for k, v in value.items():
        if len(k) == 3 and k.isupper():
            r.amounts[k] = Decimal(v)
        else:
            raise ValueError("key %r is not a currency code" % k)
    return r


default_encoders[Money] = encode_Money
default_encoders[MoneyBasket] = encode_MoneyBasket

semantic_decoders[77111] = decode_Money
semantic_decoders[77112] = decode_MoneyBasket


# Object
# ======

def encode_Object(encoder, value):
    encoder.encode_map(value.__dict__)

default_encoders[Object] = encode_Object


# Wrapper functions
# =================

default_encoder = cbor2.encoder.CBOREncoder(BytesIO())
default_encoder._encoders = default_encoders
canonical_encoder = cbor2.encoder.CBOREncoder(BytesIO())
canonical_encoder._encoders = default_encoders.copy()
canonical_encoder._encoders.update(cbor2.encoder.canonical_encoders)


def dumps(obj, canonical=False):
    encoder = canonical_encoder if canonical else default_encoder
    with BytesIO() as fp:
        encoder.fp = fp
        encoder.encode(obj)
        return fp.getvalue()


def tag_hook(decoder, tag):
    # https://cbor2.readthedocs.io/en/latest/customizing.html
    f = semantic_decoders.get(tag.tag)
    return tag if f is None else f(decoder, tag.value)


def loads(s):
    with BytesIO(s) as fp:
        return CBORDecoder(fp, tag_hook=tag_hook).decode()
