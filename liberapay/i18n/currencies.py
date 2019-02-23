from collections import defaultdict, OrderedDict
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, ROUND_UP
from numbers import Number
import operator

from mangopay.exceptions import CurrencyMismatch
from mangopay.utils import Money
import requests
import xmltodict

from ..constants import CURRENCIES, D_CENT, D_ZERO, D_MAX
from ..exceptions import InvalidNumber
from ..website import website


def _convert(self, c, rounding=ROUND_HALF_UP):
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

def _sum(cls, amounts, currency):
    a = Money.ZEROS[currency].amount
    for m in amounts:
        if m.currency != currency:
            raise CurrencyMismatch(m.currency, currency, 'sum')
        a += m.amount
    return cls(a, currency)

def _Money_init(self, amount=Decimal('0'), currency=None, rounding=None):
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
    if rounding is not None:
        minimum = Money.MINIMUMS[currency].amount
        try:
            amount = amount.quantize(minimum, rounding=rounding)
        except InvalidOperation:
            raise InvalidNumber(amount)
    if amount > D_MAX:
        raise InvalidNumber(amount)
    self.amount = amount
    self.currency = currency

def _Money_eq(self, other):
    if isinstance(other, self.__class__):
        return self.amount == other.amount and self.currency == other.currency
    if isinstance(other, (Decimal, Number)):
        return self.amount == other
    if isinstance(other, MoneyBasket):
        return other.__eq__(self)
    return False

def _Money_hash(self):
    return hash((self.currency, self.amount))

def _Money_parse(cls, amount_str, default_currency='EUR'):
    split_str = amount_str.split()
    if len(split_str) == 2:
        return Money(*split_str)
    elif len(split_str) == 1:
        return Money(split_str, default_currency)
    else:
        raise ValueError("%r is not a valid money amount" % amount_str)

def _Money_round(self, rounding=ROUND_HALF_UP):
    return Money(self.amount, self.currency, rounding=rounding)

class _Minimums(defaultdict):
    def __missing__(self, currency):
        exponent = website.db.one("SELECT get_currency_exponent(%s)", (currency,))
        minimum = Money((D_CENT if exponent == 2 else Decimal(10) ** (-exponent)), currency)
        self[currency] = minimum
        return minimum

class _Zeros(defaultdict):
    def __missing__(self, currency):
        minimum = Money.MINIMUMS[currency].amount
        zero = Money((D_ZERO if minimum is D_CENT else minimum - minimum), currency)
        self[currency] = zero
        return zero


Money.__init__ = _Money_init
Money.__nonzero__ = Money.__bool__
Money.__eq__ = _Money_eq
Money.__hash__ = _Money_hash
Money.__iter__ = lambda m: iter((m.amount, m.currency))
Money.__repr__ = lambda m: '<Money "%s">' % m
Money.__str__ = lambda m: '%(amount)s %(currency)s' % m.__dict__
Money.__unicode__ = Money.__str__
Money.convert = _convert
Money.minimum = lambda m: Money.MINIMUMS[m.currency]
Money.MINIMUMS = _Minimums()
Money.parse = classmethod(_Money_parse)
Money.round = _Money_round
Money.round_down = lambda m: m.round(ROUND_DOWN)
Money.round_up = lambda m: m.round(ROUND_UP)
Money.sum = classmethod(_sum)
Money.zero = lambda m: Money.ZEROS[m.currency]
Money.ZEROS = _Zeros()


class MoneyBasket(object):

    __slots__ = ('amounts', '__dict__')

    def __init__(self, *args, **decimals):
        self.amounts = OrderedDict(
            (currency, decimals.get(currency, Money.ZEROS[currency].amount))
            for currency in CURRENCIES
        )
        for arg in args:
            if isinstance(arg, Money):
                self.amounts[arg.currency] += arg.amount
            else:
                for m in arg:
                    self.amounts[m.currency] += m.amount

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
            return all(op(a, b) for a, b in zip(self.amounts.values(), other.amounts.values()))
        elif isinstance(other, Money):
            return op(self.amounts[other.currency], other.amount)
        elif other == 0:
            return any(op(v, 0) for v in self.amounts.values())
        else:
            raise TypeError(
                "can't compare %r and %r" % (self.__class__, other.__class__)
            )

    def __ge__(self, other):
        return self._compare(operator.ge, other)

    def __gt__(self, other):
        return self._compare(operator.gt, other)

    def __add__(self, other):
        if other is 0:
            return self
        r = self.__class__(**self.amounts)
        if isinstance(other, self.__class__):
            for currency, amount in other.amounts.items():
                if currency in r.amounts:
                    r.amounts[currency] += amount
                else:
                    r.amounts[currency] = amount
        elif isinstance(other, Money):
            currency = other.currency
            if currency in r.amounts:
                r.amounts[currency] += other.amount
            else:
                r.amounts[currency] = other.amount
        elif other == 0:
            return r
        else:
            raise TypeError(other)
        return r

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        if other is 0:
            return self
        r = self.__class__(**self.amounts)
        if isinstance(other, self.__class__):
            for currency, v in other.amounts.items():
                if currency in r.amounts:
                    r.amounts[currency] -= v
                else:
                    r.amounts[currency] = -v
        elif isinstance(other, Money):
            currency = other.currency
            if currency in r.amounts:
                r.amounts[currency] -= other.amount
            else:
                r.amounts[currency] = -other.amount
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

    __nonzero__ = __bool__

    def __setstate__(self, state):
        """Backward-compatible unpickling

        The original version of `MoneyBasket` stored `Money` objects in its
        `__dict__`, whereas the current version stores `Decimal`s in the
        `amounts` attribute.
        """
        if 'amounts' in state:
            self.amounts = state.pop('amounts')
            self.__dict__ = state
        else:
            self.amounts = {m.currency: m.amount for m in state.values()}

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
        r = Money(a, currency, rounding=rounding)
        r.fuzzy = fuzzy
        return r


def fetch_currency_exchange_rates(db):
    currencies = set(db.one("SELECT array_to_json(enum_range(NULL::currency))"))
    r = requests.get('https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml')
    rates = xmltodict.parse(r.text)['gesmes:Envelope']['Cube']['Cube']['Cube']
    for fx in rates:
        currency = fx['@currency']
        if currency not in currencies:
            continue
        db.run("""
            INSERT INTO currency_exchange_rates
                        (source_currency, target_currency, rate)
                 VALUES ('EUR', %(target)s, %(rate)s)
                      , (%(target)s, 'EUR', 1 / %(rate)s)
            ON CONFLICT (source_currency, target_currency) DO UPDATE
                    SET rate = excluded.rate
        """, dict(target=currency, rate=Decimal(fx['@rate'])))


def get_currency_exchange_rates(db):
    r = {(r[0], r[1]): r[2] for r in db.all("SELECT * FROM currency_exchange_rates")}
    if r:
        return r
    fetch_currency_exchange_rates(db)
    return get_currency_exchange_rates(db)
