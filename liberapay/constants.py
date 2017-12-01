# coding: utf8
from __future__ import print_function, unicode_literals

from collections import namedtuple, OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_UP
import re

from jinja2 import StrictUndefined
from mangopay.utils import Money
from pando.utils import utc


class CustomUndefined(StrictUndefined):
    __bool__ = __nonzero__ = lambda self: False

    def __str__(self):
        try:
            self._fail_with_undefined_error()
        except Exception as e:
            self._tell_sentry(e, {})
        return ''

    __unicode__ = __str__


def check_bits(bits):
    assert len(set(bits)) == len(bits)  # no duplicates
    assert not [b for b in bits if '{0:b}'.format(b).count('1') != 1]  # single bit


Event = namedtuple('Event', 'name bit title')


class Fees(namedtuple('Fees', ('var', 'fix'))):
    VAT = Decimal('0.17')  # 17% (Luxembourg rate)
    VAT_1 = VAT + 1

    @property
    def with_vat(self):
        r = (self.var * self.VAT_1 * 100, self.fix * self.VAT_1)
        return r[0] if not r[1] else r[1].round_up() if not r[0] else r


StandardTip = namedtuple('StandardTip', 'label weekly monthly yearly')


_ = lambda a: a

ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                "-_.")

AVATAR_QUERY = '?s=160&default=retro'
AVATAR_SOURCES = 'libravatar bitbucket facebook github google mastodon twitter'.split()

BIRTHDAY = date(2015, 5, 22)

CURRENCIES = set(('EUR', 'USD'))

D_CENT = Decimal('0.01')
D_INF = Decimal('inf')
D_UNIT = Decimal('1.00')
D_ZERO = Decimal('0.00')

DONATION_LIMITS_WEEKLY_EUR_USD = (Decimal('0.01'), Decimal('100.00'))
DONATION_LIMITS_EUR_USD = {
    'weekly': DONATION_LIMITS_WEEKLY_EUR_USD,
    'monthly': tuple((x * Decimal(52) / Decimal(12)).quantize(D_CENT, rounding=ROUND_UP)
                     for x in DONATION_LIMITS_WEEKLY_EUR_USD),
    'yearly': tuple((x * Decimal(52)).quantize(D_CENT)
                    for x in DONATION_LIMITS_WEEKLY_EUR_USD),
}
DONATION_LIMITS = {
    'EUR': {k: (Money(v[0], 'EUR'), Money(v[1], 'EUR')) for k, v in DONATION_LIMITS_EUR_USD.items()},
    'USD': {k: (Money(v[0], 'USD'), Money(v[1], 'USD')) for k, v in DONATION_LIMITS_EUR_USD.items()},
}

DOMAIN_RE = re.compile(r'''
    ^
    ([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+
    [a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?
    $
''', re.VERBOSE)

ELSEWHERE_ACTIONS = {'connect', 'lock', 'unlock'}

EMAIL_VERIFICATION_TIMEOUT = timedelta(hours=24)
EMAIL_RE = re.compile(r'''
    # This is the regexp used by MangoPay (as of February 2017).
    # It rejects some valid but exotic addresses.
    # https://en.wikipedia.org/wiki/Email_address
    ^
    [a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*
    @
    ([a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?
    $
''', re.VERBOSE)

EPOCH = datetime(1970, 1, 1, 0, 0, 0, 0, utc)

EVENTS = [
    Event('income', 1, _("When I receive money")),
    Event('low_balance', 2, _("When there isn't enough money in my wallet to cover my donations")),
    Event('withdrawal_created', 4, _("When a transfer to my bank account is initiated")),
    Event('withdrawal_failed', 8, _("When a transfer to my bank account fails")),
    Event('pledgee_joined', 16, _("When someone I pledge to joins Liberapay")),
    Event('team_invite', 32, _("When someone invites me to join a team")),
    Event('payin_bankwire_failed', 64, _("When a bank wire transfer to my Liberapay wallet fails")),
    Event('payin_bankwire_succeeded', 128, _("When a bank wire transfer to my Liberapay wallet succeeds")),
    Event('payin_bankwire_expired', 256, _("When a bank wire transfer to my Liberapay wallet expires")),
    Event('payin_directdebit_failed', 512, _("When a direct debit from my bank account fails")),
    Event('payin_directdebit_succeeded', 1024, _("When a direct debit from my bank account succeeds")),
]
check_bits([e.bit for e in EVENTS])
EVENTS = OrderedDict((e.name, e) for e in EVENTS)
EVENTS_S = ' '.join(EVENTS.keys())

# https://www.mangopay.com/pricing/
SEPA = set("""
    AT BE BG CH CY CZ DE DK EE ES ES FI FR GB GI GR HR HU IE IS IT LI LT LU LV
    MC MT NL NO PL PT RO SE SI SK
""".split())
FEE_PAYIN_BANK_WIRE = Fees(Decimal('0.005'), 0)  # 0.5%
FEE_PAYIN_CARD = {
    'EUR': Fees(Decimal('0.018'), Money('0.18', 'EUR')),  # 1.8% + €0.18
    'USD': Fees(Decimal('0.025'), Money('0.30', 'USD')),  # 2.5% + $0.30
}
FEE_PAYIN_DIRECT_DEBIT = {
    'EUR': Fees(0, Money('0.50', 'EUR')),  # €0.50
    'GBP': Fees(0, Money('0.50', 'GBP')),  # £0.50
}
FEE_PAYOUT = {
    'EUR': {
        'domestic': (SEPA, Fees(0, 0)),
        'foreign': Fees(0, Money('2.50', 'EUR')),
    },
    'GBP': {
        'domestic': ({'GB'}, Fees(0, Money('0.45', 'GBP'))),
        'foreign': Fees(0, Money('1.90', 'GBP')),
    },
    'USD': {
        '*': Fees(0, Money('3.00', 'USD')),
    },
}
FEE_PAYOUT_WARN = Decimal('0.03')  # warn user when fee exceeds 3%

INVOICE_DOC_MAX_SIZE = 5000000
INVOICE_DOCS_EXTS = ['pdf', 'jpeg', 'jpg', 'png']
INVOICE_DOCS_LIMIT = 10

INVOICE_NATURES = {
    'expense': _("Expense Report"),
}

INVOICE_STATUSES = {
    'pre': _("Draft"),
    'new': _("Sent (awaiting approval)"),
    'retracted': _("Retracted"),
    'accepted': _("Accepted (awaiting payment)"),
    'paid': _("Paid"),
    'rejected': _("Rejected"),
}

JINJA_ENV_COMMON = dict(
    trim_blocks=True, lstrip_blocks=True,
    line_statement_prefix='%',
    # undefined=CustomUndefined,
)

# https://docs.mangopay.com/api-references/kyc-rules/
KYC_DOC_MAX_SIZE = 7000000
KYC_DOC_MAX_SIZE_MB = int(KYC_DOC_MAX_SIZE / 1000000)
KYC_DOCS_EXTS = ['pdf', 'jpeg', 'jpg', 'gif', 'png']
KYC_DOCS_EXTS_STR = ', '.join(KYC_DOCS_EXTS)
KYC_INCOME_THRESHOLDS = [(i, Money(a, 'EUR')) for i, a in (
    (1, 18000),
    (2, 30000),
    (3, 50000),
    (4, 80000),
    (5, 120000),
    (6, 120000),
)]
KYC_PAYIN_YEARLY_THRESHOLD = Money('2500', 'EUR')
KYC_PAYOUT_YEARLY_THRESHOLD = Money('1000', 'EUR')

LAUNCH_TIME = datetime(2016, 2, 3, 12, 50, 0, 0, utc)

PARTICIPANT_KINDS = {
    'individual': _("Individual"),
    'organization': _("Organization"),
    'group': _("Team"),
}

PASSWORD_MIN_SIZE = 8
PASSWORD_MAX_SIZE = 150

PAYIN_BANK_WIRE_MIN = {k: Money('2.00', k) for k in ('EUR', 'USD')}  # fee ≈ 0.99%
PAYIN_BANK_WIRE_TARGET = {k: Money('5.00', k) for k in ('EUR', 'USD')}  # fee ≈ 0.6%
PAYIN_BANK_WIRE_MAX = {k: Money('2500.00', k) for k in ('EUR', 'USD')}
PAYIN_CARD_MIN = {
    'EUR': Money('15.00', 'EUR'),  # fee ≈ 3.5%
    'USD': Money('20.00', 'USD'),  # fee ≈ 4.58%
}
PAYIN_CARD_TARGET = {
    'EUR': Money('92.00', 'EUR'),  # fee ≈ 2.33%
    'USD': Money('95.00', 'USD'),  # fee ≈ 3.27%
}
PAYIN_CARD_MAX = {k: Money('2500.00', k) for k in ('EUR', 'USD')}
PAYIN_DIRECT_DEBIT_MIN_EUR_GBP = Decimal('15.00')  # fee ≈ 3.78%
PAYIN_DIRECT_DEBIT_MIN = {
    'EUR': Money(PAYIN_DIRECT_DEBIT_MIN_EUR_GBP, 'EUR'),
    'GBP': Money(PAYIN_DIRECT_DEBIT_MIN_EUR_GBP, 'GBP'),
}
PAYIN_DIRECT_DEBIT_TARGET_EUR_GBP = Decimal('99.00')  # fee ≈ 0.59%
PAYIN_DIRECT_DEBIT_TARGET = {
    'EUR': Money(PAYIN_DIRECT_DEBIT_TARGET_EUR_GBP, 'EUR'),
    'GBP': Money(PAYIN_DIRECT_DEBIT_TARGET_EUR_GBP, 'GBP'),
}
PAYIN_DIRECT_DEBIT_MAX = {k: Money('2500.00', k) for k in ('EUR', 'USD')}

PERIOD_CONVERSION_RATES = {
    'weekly': Decimal(1),
    'monthly': Decimal(12) / Decimal(52),
    'yearly': Decimal(1) / Decimal(52),
}

POSTAL_ADDRESS_KEYS = (
    'AddressLine1', 'AddressLine2', 'City', 'Region', 'PostalCode', 'Country'
)

PRIVACY_FIELDS = OrderedDict([
    ('hide_giving', _("Hide total giving from others.")),
    ('hide_receiving', _("Hide total receiving from others.")),
    ('hide_from_search', _("Hide myself from search results on Liberapay.")),
    ('profile_noindex', _("Tell web search engines not to index my profile.")),
    ('hide_from_lists', _("Prevent my profile from being listed on Liberapay.")),
])
PRIVACY_FIELDS_S = ' '.join(PRIVACY_FIELDS.keys())

PRIVILEGES = dict(admin=1, run_payday=2)
check_bits(list(PRIVILEGES.values()))

QUARANTINE = timedelta(weeks=4)

RATE_LIMITS = {
    'add_email.source': (5, 60*60*24),  # 5 per day
    'add_email.target': (2, 60*60*24),  # 2 per day
    'change_username': (7, 60*60*24*7),  # 7 per week
    'log-in.email': (10, 60*60*24),  # 10 per day
    'log-in.email.not-verified': (2, 60*60*24),  # 2 per day
    'log-in.email.verified': (10, 60*60*24),  # 10 per day
    'log-in.password': (3, 60*60),  # 3 per hour
    'sign-up.ip-addr': (5, 60*60),  # 5 per hour per IP address
    'sign-up.ip-net': (15, 15*60),  # 15 per 15 minutes per IP network
    'sign-up.ip-version': (15, 15*60),  # 15 per 15 minutes per IP version
}

SESSION = str('session')  # bytes in python2, unicode in python3
SESSION_REFRESH = timedelta(hours=1)
SESSION_TIMEOUT = timedelta(hours=6)


def make_standard_tip(label, weekly, currency):
    return StandardTip(
        label,
        Money(weekly, currency),
        Money(weekly / PERIOD_CONVERSION_RATES['monthly'], currency),
        Money(weekly / PERIOD_CONVERSION_RATES['yearly'], currency),
    )


STANDARD_TIPS_EUR_USD = (
    (_("Symbolic"), Decimal('0.01')),
    (_("Small"), Decimal('0.25')),
    (_("Medium"), Decimal('1.00')),
    (_("Large"), Decimal('5.00')),
    (_("Maximum"), DONATION_LIMITS_EUR_USD['weekly'][1]),
)
STANDARD_TIPS = {
    'EUR': [make_standard_tip(label, weekly, 'EUR') for label, weekly in STANDARD_TIPS_EUR_USD],
    'USD': [make_standard_tip(label, weekly, 'USD') for label, weekly in STANDARD_TIPS_EUR_USD],
}

SUMMARY_MAX_SIZE = 100

TAKE_THROTTLING_THRESHOLD = {k: Money('1.00', k) for k in ('EUR', 'USD')}

USERNAME_MAX_SIZE = 32

ZERO = {c: Money(D_ZERO, c) for c in ('EUR', 'USD', None)}

del _
