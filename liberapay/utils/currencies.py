from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal, ROUND_DOWN, ROUND_UP

from mangopay.utils import Money
import requests
import xmltodict

from liberapay.constants import D_CENT, D_ZERO
from liberapay.website import website


def _convert(self, c):
    if self.currency == c:
        return self
    amount = self.amount * website.currency_exchange_rates[(self.currency, c)]
    return Money(amount.quantize(D_CENT), c)


Money.__nonzero__ = Money.__bool__
Money.__eq__ = lambda a, b: a.__dict__ == b.__dict__ if isinstance(b, Money) else a.amount == b
Money.__iter__ = lambda m: iter((m.amount, m.currency))
Money.__repr__ = lambda m: '<Money "%s">' % m
Money.__str__ = lambda m: '%(amount)s %(currency)s' % m.__dict__
Money.__unicode__ = Money.__str__
Money.convert = _convert
Money.int = lambda m: Money(int(m.amount * 100), m.currency)
Money.round_down = lambda m: Money(m.amount.quantize(D_CENT, rounding=ROUND_DOWN), m.currency)
Money.round_up = lambda m: Money(m.amount.quantize(D_CENT, rounding=ROUND_UP), m.currency)
Money.zero = lambda m: Money(D_ZERO, m.currency)


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
