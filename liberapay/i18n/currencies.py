from datetime import datetime, timedelta, timezone
from decimal import (
    Decimal, InvalidOperation, ROUND_DOWN, ROUND_FLOOR, ROUND_HALF_UP, ROUND_UP,
)
from itertools import chain
from numbers import Number
import operator
from threading import Lock

import requests

from ..exceptions import InvalidNumber
from ..website import website


CURRENCIES = dict.fromkeys([
    'AED', 'AFN', 'ALL', 'AMD', 'ANG', 'AOA', 'ARS', 'AUD', 'AWG', 'AZN', 'BAM',
    'BBD', 'BDT', 'BGN', 'BIF', 'BMD', 'BND', 'BOB', 'BRL', 'BSD', 'BWP', 'BYN',
    'BZD', 'CAD', 'CDF', 'CHF', 'CLP', 'CNY', 'COP', 'CRC', 'CVE', 'CZK', 'DJF',
    'DKK', 'DOP', 'DZD', 'EGP', 'ETB', 'EUR', 'FJD', 'FKP', 'GBP', 'GEL', 'GIP',
    'GMD', 'GNF', 'GTQ', 'GYD', 'HKD', 'HNL', 'HTG', 'HUF', 'IDR', 'ILS', 'INR',
    'ISK', 'JMD', 'JPY', 'KES', 'KGS', 'KHR', 'KMF', 'KRW', 'KYD', 'KZT', 'LAK',
    'LBP', 'LKR', 'LRD', 'LSL', 'MAD', 'MDL', 'MGA', 'MKD', 'MMK', 'MNT', 'MOP',
    'MUR', 'MVR', 'MWK', 'MXN', 'MYR', 'MZN', 'NAD', 'NGN', 'NIO', 'NOK', 'NPR',
    'NZD', 'PAB', 'PEN', 'PGK', 'PHP', 'PKR', 'PLN', 'PYG', 'QAR', 'RON', 'RSD',
    'RUB', 'RWF', 'SAR', 'SBD', 'SCR', 'SEK', 'SGD', 'SHP', 'SLE', 'SOS', 'SRD',
    'SZL', 'THB', 'TJS', 'TOP', 'TRY', 'TTD', 'TWD', 'TZS', 'UAH', 'UGX', 'USD',
    'UYU', 'UZS', 'VND', 'VUV', 'WST', 'XAF', 'XCD', 'XOF', 'XPF', 'YER', 'ZAR',
    'ZMW',
])

CURRENCY_REPLACEMENTS = {
    'HRK': (Decimal('7.53450'), 'EUR', datetime(2023, 1, 1, 1, 0, 0, tzinfo=timezone.utc)),
}

ZERO_DECIMAL_CURRENCIES = {
    # https://stripe.com/docs/currencies#presentment-currencies
    'stripe': {
        'BIF', 'CLP', 'DJF', 'GNF', 'JPY', 'KMF', 'KRW', 'MGA', 'PYG', 'RWF',
        'VND', 'VUV', 'XAF', 'XOF', 'XPF',
    },
}
ZERO_DECIMAL_CURRENCIES['any'] = set(chain(*ZERO_DECIMAL_CURRENCIES.values()))
UNDIVIDABLE_CURRENCIES = {
    # https://developer.paypal.com/reference/currency-codes/
    'paypal': {'HUF', 'JPY', 'TWD'},
    # https://stripe.com/docs/currencies#presentment-currencies
    'stripe': ZERO_DECIMAL_CURRENCIES['stripe'] | {'HUF', 'ISK', 'TWD', 'UGX'},
}
UNDIVIDABLE_CURRENCIES['any'] = set(chain(*UNDIVIDABLE_CURRENCIES.values()))


D_CENT = Decimal('0.01')
D_MAX = Decimal('999999999999.99')
D_ONE = Decimal('1')
D_ZERO = Decimal('0')
D_ZERO_CENT = Decimal('0.00')


class CurrencyMismatch(ValueError):
    pass


class _Minimums(dict):
    def __missing__(self, currency):
        minimum = Money(
            D_ONE if currency in UNDIVIDABLE_CURRENCIES['any'] else D_CENT,
            currency
        )
        self[currency] = minimum
        return minimum

class _Zeros(dict):
    def __missing__(self, currency):
        zero = Money(
            D_ZERO if currency in UNDIVIDABLE_CURRENCIES['any'] else D_ZERO_CENT,
            currency
        )
        self[currency] = zero
        return zero


class Money:
    __slots__ = ('amount', 'currency', 'fuzzy')

    MINIMUMS = _Minimums()
    ZEROS = _Zeros()

    def __init__(self, amount=Decimal('0'), currency=None, rounding=None, fuzzy=False):
        if not isinstance(amount, Decimal):
            try:
                amount = Decimal(str(amount))
            except InvalidOperation:
                raise InvalidNumber(amount)
            # Why `str(amount)`? Because:
            # >>> Decimal(0.23)
            # Decimal('0.2300000000000000099920072216264088638126850128173828125')
            # >>> Decimal(str(0.23))
            # Decimal('0.23')
        if amount > D_MAX and not amount.is_infinite():
            raise InvalidNumber(amount)
        if rounding is not None:
            minimum = Money.MINIMUMS[currency].amount
            try:
                amount = amount.quantize(minimum, rounding=rounding)
            except InvalidOperation:
                raise InvalidNumber(str(amount))
        self.amount = amount
        self.currency = currency
        self.fuzzy = fuzzy

    def __abs__(self):
        return self.__class__(abs(self.amount), self.currency)

    def __add__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '+')
            other = other.amount
        amount = self.amount + other
        return self.__class__(amount, self.currency)

    def __bool__(self):
        return bool(self.amount)

    def __ceil__(self):
        return self.__class__(self.amount.__ceil__(), self.currency)

    def __divmod__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, 'divmod')
            if other.amount == 0:
                raise ZeroDivisionError()
            return divmod(self.amount, other.amount)
        if isinstance(other, (Decimal, Number)):
            if other == 0:
                raise ZeroDivisionError()
            whole, remainder = divmod(self.amount, other)
            return (self.__class__(whole, self.currency),
                    self.__class__(remainder, self.currency))
        return NotImplemented

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.amount == other.amount and self.currency == other.currency
        if isinstance(other, (Decimal, Number)):
            return self.amount == other
        if isinstance(other, MoneyBasket):
            return other.__eq__(self)
        return False

    def __float__(self):
        return float(self.amount)

    def __floor__(self):
        return self.__class__(self.amount.__floor__(), self.currency)

    def __floordiv__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '//')
            if other.amount == 0:
                raise ZeroDivisionError()
            return self.amount // other.amount
        if isinstance(other, (Decimal, Number)):
            if other == 0:
                raise ZeroDivisionError()
            amount = self.amount // other
            return self.__class__(amount, self.currency)
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '>=')
            other = other.amount
        return self.amount >= other

    def __gt__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '>')
            other = other.amount
        return self.amount > other

    def __hash__(self):
        return hash((self.currency, self.amount))

    def __int__(self):
        return int(self.amount)

    def __iter__(self):
        return iter((self.amount, self.currency))

    def __le__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '<=')
            other = other.amount
        return self.amount <= other

    def __lt__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '<')
            other = other.amount
        return self.amount < other

    def __mod__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '%')
            return self.amount % other.amount
        if isinstance(other, (Decimal, Number)):
            if other == 0:
                raise ZeroDivisionError()
            return self.__class__(self.amount % other, self.currency)
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, Money):
            raise TypeError("multiplying two sums of money isn't supported")
        return self.__class__(self.amount * other, self.currency)

    def __ne__(self, other):
        return not self == other

    def __neg__(self):
        return self.__class__(-self.amount, self.currency)

    def __pos__(self):
        return self.__class__(+self.amount, self.currency)

    def __pow__(self, other):
        if isinstance(other, Money):
            raise TypeError("multiplying two sums of money isn't supported")
        return self.__class__(self.amount ** other, self.currency)

    def __radd__(self, other):
        return self.__add__(other)

    def __repr__(self):
        return f'<Money "{self}">'

    def __round__(self, ndigits=0):
        return self.__class__(round(self.amount, ndigits), self.currency)

    def __rsub__(self, other):
        return (-self).__add__(other)

    def __str__(self):
        return f'{self.amount} {self.currency}'

    def __sub__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '-')
            other = other.amount
        return self.__class__(self.amount - other, self.currency)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, Money):
            if other.currency != self.currency:
                raise CurrencyMismatch(self.currency, other.currency, '/')
            if other.amount == 0:
                raise ZeroDivisionError()
            return self.amount / other.amount
        if isinstance(other, (Decimal, Number)):
            if other == 0:
                raise ZeroDivisionError()
            return self.__class__(self.amount / other, self.currency)
        return NotImplemented

    def __trunc__(self):
        return self.__class__(self.amount.__trunc__(), self.currency)

    def convert(self, c, rounding=ROUND_HALF_UP):
        if self.currency == c:
            return self
        if 'EUR' in (self.currency, c):
            rate = website.currency_exchange_rates[(self.currency, c)]
        else:
            rate = (
                website.currency_exchange_rates[(self.currency, 'EUR')] *
                website.currency_exchange_rates[('EUR', c)]
            )
        amount = self.amount * rate
        return Money(amount, c, rounding=rounding)

    def convert_if_currency_is_phased_out(self):
        if self.currency not in CURRENCIES:
            replacement = CURRENCY_REPLACEMENTS.get(self.currency)
            if replacement:
                rate, new_currency, time_of_switch = replacement
                return Money(self.amount / rate, new_currency)
        return self

    def for_json(self):
        return {'amount': str(self.amount), 'currency': self.currency}

    def minimum(self):
        return self.MINIMUMS[self.currency]

    @classmethod
    def parse(cls, amount_str, default_currency='EUR'):
        split_str = amount_str.split()
        if len(split_str) == 2:
            return Money(*split_str)
        elif len(split_str) == 1:
            return Money(split_str, default_currency)
        else:
            raise ValueError("%r is not a valid money amount" % amount_str)

    def round(self, rounding=ROUND_HALF_UP, allow_zero=True):
        r = Money(self.amount, self.currency, rounding=rounding)
        if not allow_zero:
            if self.amount == 0:
                raise ValueError("can't round zero away from zero")
            if r.amount == 0:
                return self.minimum() if self.amount > 0 else -self.minimum()
        return r

    def round_down(self):
        return self.round(ROUND_DOWN)

    def round_up(self):
        return self.round(ROUND_UP)

    @classmethod
    def sum(cls, amounts, currency):
        a = Money.ZEROS[currency].amount
        for m in amounts:
            if m.currency != currency:
                raise CurrencyMismatch(m.currency, currency, 'sum')
            a += m.amount
        return cls(a, currency)

    def zero(self):
        return self.ZEROS[self.currency]


class MoneyBasketAmounts(dict):

    def __missing__(self, currency):
        return Money.ZEROS[currency].amount

    def __setitem__(self, currency, amount):
        if amount:
            super().__setitem__(currency, amount)
        else:
            self.pop(currency, None)


class MoneyBasket:

    __slots__ = ('amounts', '__dict__')

    def __init__(self, *args, **decimals):
        self.amounts = MoneyBasketAmounts()
        for arg in args:
            if isinstance(arg, Money):
                self.amounts[arg.currency] += arg.amount
            elif isinstance(arg, MoneyBasketAmounts):
                for currency, amount in arg.items():
                    self.amounts[currency] += amount
            else:
                for m in arg:
                    self.amounts[m.currency] += m.amount
        for currency, amount in decimals.items():
            self.amounts[currency] = amount

    def __getitem__(self, currency):
        return Money(self.amounts[currency], currency)

    def __iter__(self):
        return (Money(amount, currency) for currency, amount in self.amounts.items())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.amounts == other.amounts
        elif isinstance(other, Money):
            return self.amounts == MoneyBasket(other).amounts
        elif other == 0:
            return all(v == 0 for v in self.amounts.values())
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def _compare(self, op, other):
        if isinstance(other, self.__class__):
            return self.amounts.items() == other.amounts.items()
        elif other == 0:
            return all(op(v, 0) for v in self.amounts.values())
        else:
            raise TypeError(
                "can't compare %r and %r" % (self.__class__, other.__class__)
            )

    def __ge__(self, other):
        return self._compare(operator.ge, other)

    def __gt__(self, other):
        return self._compare(operator.gt, other)

    def __add__(self, other):
        if other == 0:
            return self
        r = self.__class__(self.amounts)
        if isinstance(other, self.__class__):
            for currency, amount in other.amounts.items():
                r.amounts[currency] += amount
        elif isinstance(other, Money):
            r.amounts[other.currency] += other.amount
        else:
            raise TypeError(other)
        return r

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        if other == 0:
            return self
        r = self.__class__(self.amounts)
        if isinstance(other, self.__class__):
            for currency, v in other.amounts.items():
                r.amounts[currency] -= v
        elif isinstance(other, Money):
            r.amounts[other.currency] -= other.amount
        else:
            raise TypeError(other)
        return r

    def __repr__(self):
        return '%s[%s]' % (
            self.__class__.__name__,
            ', '.join('%s %s' % (a, c) for c, a in self.amounts.items() if a)
        )

    def __bool__(self):
        return any(v for v in self.amounts.values())

    @property
    def currencies_present(self):
        return [k for k, v in self.amounts.items() if v > 0]

    def fuzzy_sum(self, currency, rounding=ROUND_UP):
        a = Money.ZEROS[currency].amount
        fuzzy = False
        for m in self:
            if m.currency == currency:
                a += m.amount
            elif m.amount:
                a += m.convert(currency, rounding=None).amount
                fuzzy = True
        return Money(a, currency, rounding=rounding, fuzzy=fuzzy)


def to_precision(x, precision, rounding=ROUND_HALF_UP):
    """Round `x` to keep only `precision` of its most significant digits.

    >>> to_precision(Decimal('0.0086820'), 2)
    Decimal('0.0087')
    >>> to_precision(Decimal('13567.89'), 3)
    Decimal('13600')
    >>> to_precision(Decimal('0.000'), 4)
    Decimal('0')
    """
    if x == 0:
        return Decimal(0)
    log10 = x.log10().to_integral(ROUND_FLOOR)
    # round
    factor = Decimal(10) ** (log10 + 1)
    r = (x / factor).quantize(Decimal(10) ** -precision, rounding=rounding) * factor
    # remove trailing zeros
    r = r.quantize(Decimal(10) ** (log10 - precision + 1))
    return r


def convert_symbolic_amount(amount, target_currency, precision=2, rounding=ROUND_HALF_UP):
    rate = website.currency_exchange_rates[('EUR', target_currency)]
    minimum = Money.MINIMUMS[target_currency].amount
    return max(
        to_precision(amount * rate, precision, rounding).quantize(minimum, rounding),
        minimum
    )


class MoneyAutoConvertDict(dict):
    __slots__ = ('constants', 'precision')

    instances = []
    # Note: our instances of this class aren't ephemeral, so a simple list is
    #       intentionally used here instead of weak references.
    lock = Lock()

    def __init__(self, constant_items, precision=2):
        super().__init__(constant_items)
        self.constants = set(constant_items.keys())
        self.precision = precision
        self.instances.append(self)

    def __delitem__(self):
        raise NotImplementedError()

    def __ior__(self):
        raise NotImplementedError()

    def __missing__(self, currency):
        with self.lock:
            r = self.generate_value(currency)
            dict.__setitem__(self, currency, r)
        return r

    def __setitem__(self):
        raise NotImplementedError()

    def clear(self):
        """Clear all the auto-converted amounts.
        """
        with self.lock:
            for currency in list(self):
                if currency not in self.constants:
                    dict.__delitem__(self, currency)

    def generate_value(self, currency):
        return Money(
            convert_symbolic_amount(self['EUR'].amount, currency, self.precision),
            currency,
            rounding=ROUND_UP,
        )

    def pop(self):
        raise NotImplementedError()

    def popitem(self):
        raise NotImplementedError()

    def update(self):
        raise NotImplementedError()


def fetch_currency_exchange_rates(db=None):
    db = db or website.db
    currencies = set(db.one("SELECT array_to_json(enum_range(NULL::currency))"))
    currencies.remove('EUR')
    if (access_key := website.app_conf.fixer_access_key):
        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        r = requests.get(
            f'https://data.fixer.io/api/{yesterday}?access_key={access_key}&base=EUR'
        )
    else:
        assert website.env.instance_type != 'production'
        r = requests.get('https://liberapay.com/data/exchange-rates.json')
    rates = r.json()['rates']
    for currency, rate in rates.items():
        if currency not in currencies:
            continue
        db.run("""
            INSERT INTO currency_exchange_rates
                        (source_currency, target_currency, rate)
                 VALUES ('EUR', %(target)s, %(rate)s)
                      , (%(target)s, 'EUR', 1 / %(rate)s)
            ON CONFLICT (source_currency, target_currency) DO UPDATE
                    SET rate = excluded.rate
        """, dict(target=currency, rate=Decimal(str(rate))))
        currencies.remove(currency)
    # Update the local cache, unless it hasn't been created yet.
    if hasattr(website, 'currency_exchange_rates'):
        website.currency_exchange_rates = get_currency_exchange_rates(db)
    # Clear the cached auto-converted money amounts, so they'll be recomputed
    # with the new exchange rates.
    for d in MoneyAutoConvertDict.instances:
        d.clear()
    # Check for missing exchange rates.
    if currencies:
        raise Exception(
            f"missing exchange rates for currencies {', '.join(currencies)}"
        )


def get_currency_exchange_rates(db):
    r = {(r[0], r[1]): r[2] for r in db.all("SELECT * FROM currency_exchange_rates")}
    if r:
        return r
    fetch_currency_exchange_rates(db)
    return get_currency_exchange_rates(db)
