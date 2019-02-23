# Monetary values in CBOR

This document describes two tags for the serialization of money amounts in Concise Binary Object Representation (CBOR, [RFC7049](https://tools.ietf.org/html/rfc7049)).

## Common rules

### Currency codes

Currency codes *should* be valid 3-letter codes from the [ISO 4217](https://en.wikipedia.org/wiki/ISO_4217) standard. CBOR encoders and decoders *may* reject invalid or unknown currency codes.

### Numbers

Multiple ways of serializing a quantity of money are allowed:

- As a UTF-8 string (major type 3), in base 10 with `.` (U+002E) as the decimal separator. That is, the string *must* match the Perl-compatible regular expression `[0-9]+(\.[0-9]+)?`.
- As an integer (major types 1 and 2).
- As a big number ([tags 2 and 3](https://tools.ietf.org/html/rfc7049#section-2.4.2)).
- As a decimal fraction or big float ([tags 4 and 5](https://tools.ietf.org/html/rfc7049#section-2.4.3)).
- As an arbitrary-exponent number ([tags 264 and 265](http://peteroupc.github.io/CBOR/bigfrac.html)).

## Tag 77111: Money

- Data item: UTF-8 string (major type 3) or array (major type 4)
- Semantics: an amount of money, represented as a number and a currency code

The string representation is composed of a currency code (three uppercase letters) followed by a number. It *must* match the Perl-compatible regular expression `[A-Z]{3}[0-9]+(\.[0-9]+)?`.

Examples: `EUR10.00`, `JPY1300`.

The array representation is composed of two or three elements:

1. The currency code (major type 3).
2. The quantity of money (in any of the allowed formats listed in the previous section).
3. A map (major type 5) of additional attributes attached to this amount of money. The map's keys *should* be text strings (major type 3) and a decoder *should* return an error if it encounters an attribute that it cannot attach to the re-created object.

Examples: `["EUR", "10.00"]`, `["JPY", 1300, {"fuzzy": true}]`.

## Tag 77112: MoneyBasket

- Data item: map (major type 5)
- Semantics: a set of money amounts in different currencies

The map's keys *should* be either currency codes or the special value `"attrs"`.

If the key is a currency code, then the value *must* be a number serialized in one of the allowed formats previously listed.

If the key is `"attrs"`, then the value *must* be a map (major type 5) of additional attributes attached to this basket. The map's keys *should* be text strings (major type 3) and a decoder *should* return an error if it encounters an attribute that it cannot attach to the re-created object.

Examples: `{"EUR": 10.00}`, `{"JPY": "1300", "USD": "11.22"}`, `{"XAF": 0, "attrs": {"foo": "bar"}}`.

## Implementations

- Initial implementation: https://github.com/liberapay/liberapay.com/blob/2920b3c8ade10a8555a5b1095d1834c8d7cc0d55/liberapay/utils/cbor.py#L42-L83

## Trivia

The tag number 77111 was chosen because it represents the first two letters of the word "Money" in ASCII.

## Author and License

The present document was written by Charly Coste (changaco at changaco.oy.lc) on 2019-02-22 and released on the same day under the terms of the [CC0 Public Domain Dedication](https://creativecommons.org/publicdomain/zero/1.0/).
