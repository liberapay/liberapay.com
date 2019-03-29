from collections import defaultdict, namedtuple, OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, ROUND_UP
import re

from mangopay.utils import Money
from markupsafe import Markup
from pando.utils import utc


def ordered_set(keys):
    return OrderedDict((k, None) for k in keys)


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


def to_precision(x, precision, rounding=ROUND_HALF_UP):
    if not x:
        return x
    # round
    factor = Decimal(10) ** (x.log10().to_integral(ROUND_FLOOR) + 1)
    r = (x / factor).quantize(Decimal(10) ** -precision, rounding=rounding) * factor
    # remove trailing zeros
    r = r.quantize(Decimal(10) ** (int(x.log10()) - precision + 1))
    return r


def convert_symbolic_amount(amount, target_currency, precision=2, rounding=ROUND_HALF_UP):
    from liberapay.website import website
    rate = website.currency_exchange_rates[('EUR', target_currency)]
    return to_precision(amount * rate, precision, rounding)


class MoneyAutoConvertDict(defaultdict):

    def __init__(self, *args, **kw):
        super(MoneyAutoConvertDict, self).__init__(None, *args, **kw)

    def __missing__(self, currency):
        r = Money(convert_symbolic_amount(self['EUR'].amount, currency, 1), currency)
        self[currency] = r
        return r


StandardTip = namedtuple('StandardTip', 'label weekly monthly yearly')


_ = lambda a: a

ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                "-_.")

AVATAR_QUERY = '?s=160&default=retro'
AVATAR_SOURCES = (
    'libravatar bitbucket facebook github gitlab google mastodon twitch twitter youtube'
).split()

BASE64URL_CHARS = set('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_')

BIRTHDAY = date(2015, 5, 22)

CURRENCIES = ordered_set([
    'EUR', 'USD',
    'AUD', 'BGN', 'BRL', 'CAD', 'CHF', 'CNY', 'CZK', 'DKK', 'GBP', 'HKD', 'HRK',
    'HUF', 'IDR', 'ILS', 'INR', 'ISK', 'JPY', 'KRW', 'MXN', 'MYR', 'NOK', 'NZD',
    'PHP', 'PLN', 'RON', 'RUB', 'SEK', 'SGD', 'THB', 'TRY', 'ZAR'
])

D_CENT = Decimal('0.01')
D_MAX = Decimal('999999999999.99')
D_ZERO = Decimal('0.00')

class _DonationLimits(defaultdict):
    def __missing__(self, currency):
        r = {
            period: (
                Money(convert_symbolic_amount(eur_amounts[0], currency, rounding=ROUND_UP), currency),
                Money(convert_symbolic_amount(eur_amounts[1], currency, rounding=ROUND_UP), currency)
            ) for period, eur_amounts in DONATION_LIMITS_EUR_USD.items()
        }
        self[currency] = r
        return r

DONATION_LIMITS_WEEKLY_EUR_USD = (Decimal('0.01'), Decimal('100.00'))
DONATION_LIMITS_EUR_USD = {
    'weekly': DONATION_LIMITS_WEEKLY_EUR_USD,
    'monthly': tuple((x * Decimal(52) / Decimal(12)).quantize(D_CENT, rounding=ROUND_UP)
                     for x in DONATION_LIMITS_WEEKLY_EUR_USD),
    'yearly': tuple((x * Decimal(52)).quantize(D_CENT)
                    for x in DONATION_LIMITS_WEEKLY_EUR_USD),
}
DONATION_LIMITS = _DonationLimits(None, {
    'EUR': {k: (Money(v[0], 'EUR'), Money(v[1], 'EUR')) for k, v in DONATION_LIMITS_EUR_USD.items()},
    'USD': {k: (Money(v[0], 'USD'), Money(v[1], 'USD')) for k, v in DONATION_LIMITS_EUR_USD.items()},
})

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

EUROZONE = set("AT BE CY DE EE ES FI FR GR IE IT LT LU LV MT NL PT SI SK".split())
SEPA = EUROZONE | set("AD BG CH CZ DK GB GI HR HU IS LI MC NO PL RO SE VA".split())

EVENTS = [
    Event('income', 1, _("Every week as long as I am receiving donations")),
    Event('donate_reminder', 2, _("When it's time to renew my donations")),
    Event('withdrawal_created', 4, _("When a transfer to my bank account is initiated")),
    Event('withdrawal_failed', 8, _("When a transfer to my bank account fails")),
    Event('pledgee_joined', 16, _("When someone I pledge to joins Liberapay")),
    Event('team_invite', 32, _("When someone invites me to join a team")),
    Event('payin_failed', 2**11, _("When a payment I initiated fails")),
    Event('payin_succeeded', 2**12, _("When a payment I initiated succeeds")),
]
check_bits([e.bit for e in EVENTS])
EVENTS = OrderedDict((e.name, e) for e in EVENTS)
EVENTS_S = ' '.join(EVENTS.keys())

# https://www.mangopay.com/pricing/
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
        'foreign': Fees(0, 0),
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

HTML_A = Markup('<a href="%s">%s</a>')

IDENTITY_FIELDS = set("""
    birthdate headquarters_address name nationality occupation organization_name
    postal_address
""".split())

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
PAYIN_DIRECT_DEBIT_COUNTRIES = {
    # https://support.gocardless.com/hc/en-gb/articles/115005758445
    'EUR': EUROZONE | set("MC SM".split()),
}
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

PAYIN_PAYPAL_MIN_ACCEPTABLE = MoneyAutoConvertDict({  # fee > 10%
    'EUR': Money('2.00', 'EUR'),
    'USD': Money('2.00', 'USD'),
})
PAYIN_PAYPAL_MIN_RECOMMENDED = MoneyAutoConvertDict({  # fee < 8%
    'EUR': Money('10.00', 'EUR'),
    'USD': Money('12.00', 'USD'),
})
PAYIN_PAYPAL_LOW_FEE = MoneyAutoConvertDict({  # fee < 6%
    'EUR': Money('40.00', 'EUR'),
    'USD': Money('48.00', 'USD'),
})
PAYIN_PAYPAL_MAX_ACCEPTABLE = MoneyAutoConvertDict({
    'EUR': Money('5000.00', 'EUR'),
    'USD': Money('5000.00', 'USD'),
})

PAYIN_STRIPE_MIN_ACCEPTABLE = MoneyAutoConvertDict({  # fee > 10%
    'EUR': Money('2.00', 'EUR'),
    'USD': Money('2.00', 'USD'),
})
PAYIN_STRIPE_MIN_RECOMMENDED = MoneyAutoConvertDict({  # fee < 8%
    'EUR': Money('10.00', 'EUR'),
    'USD': Money('12.00', 'USD'),
})
PAYIN_STRIPE_LOW_FEE = MoneyAutoConvertDict({  # fee < 6%
    'EUR': Money('40.00', 'EUR'),
    'USD': Money('48.00', 'USD'),
})
PAYIN_STRIPE_MAX_ACCEPTABLE = MoneyAutoConvertDict({
    'EUR': Money('5000.00', 'EUR'),
    'USD': Money('5000.00', 'USD'),
})

PAYMENT_METHODS = {
    'mango-ba': _("Direct Debit"),
    'mango-bw': _("Bank Wire"),
    'mango-cc': _("Credit Card"),
}
PAYMENT_SLUGS = {
    'mango-ba': 'direct-debit',
    'mango-bw': 'bankwire',
    'mango-cc': 'card',
}

PAYOUT_COUNTRIES = {
    'paypal': set("""
        AD AE AG AI AL AM AN AO AR AT AU AW AZ BA BB BE BF BG BH BI BJ BM BN BO
        BR BS BT BW BY BZ C2 CA CD CG CH CI CK CL CM CO CR CV CY CZ DE DJ DK DM
        DO DZ EC EE EG ER ES ET FI FJ FK FM FO FR GA GD GE GF GI GL GM GN GP GR
        GT GW GY HK HN HR HU ID IE IL IN IS IT JM JO JP KE KG KH KI KM KN KR KW
        KY KZ LA LC LI LK LS LT LU LV MA MC MD ME MG MH MK ML MN MQ MR MS MT MU
        MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PL
        PM PN PT PW PY QA RE RO RS RU RW SA SB SC SE SG SH SI SJ SK SL SM SN SO
        SR ST SV SZ TC TD TG TH TJ TM TN TO TT TT TT TT TV TW TZ UA UG GB US UY
        VA VC VE VG VN VU WF WS YE YT ZA ZM ZW
        PR
    """.split()),  # https://www.paypal.com/us/webapps/mpp/country-worldwide

    'stripe': set("""
        AT AU BE CA CH DE DK ES FI FR GB HK IE IT JP LU NL NO NZ PT SE SG US
        PR
    """.split()),  # https://stripe.com/global
}

PERIOD_CONVERSION_MAP = {
    ('weekly', 'weekly'): Decimal(1),
    ('monthly', 'weekly'): Decimal(12) / Decimal(52),
    ('yearly', 'weekly'): Decimal(1) / Decimal(52),
    ('weekly', 'monthly'): Decimal(52) / Decimal(12),
    ('monthly', 'monthly'): Decimal(1),
    ('yearly', 'monthly'): Decimal(1) / Decimal(12),
    ('weekly', 'yearly'): Decimal(52),
    ('monthly', 'yearly'): Decimal(12),
    ('yearly', 'yearly'): Decimal(1),
}

PERIOD_CONVERSION_RATES = {
    'weekly': Decimal(1),
    'monthly': Decimal(12) / Decimal(52),
    'yearly': Decimal(1) / Decimal(52),
}

POSTAL_ADDRESS_KEYS = (
    'AddressLine1', 'AddressLine2', 'City', 'Region', 'PostalCode', 'Country'
)
POSTAL_ADDRESS_KEYS_LIBERAPAY = (
    'country', 'region', 'city', 'postal_code', 'local_address'
)
POSTAL_ADDRESS_KEYS_STRIPE = (
    'line1', 'line2', 'city', 'state', 'postal_code', 'country'
)

PRIVACY_FIELDS = OrderedDict([
    ('hide_giving', (_("Hide total giving from others."), False)),
    ('hide_receiving', (_("Hide total receiving from others."), False)),
    ('hide_from_search', (_("Hide this profile from search results on Liberapay."), True)),
    ('profile_noindex', (_("Tell web search engines not to index this profile."), True)),
    ('hide_from_lists', (_("Prevent this profile from being listed on Liberapay."), True)),
])
PRIVACY_FIELDS_S = ' '.join(PRIVACY_FIELDS.keys())

PRIVILEGES = dict(admin=1, run_payday=2)
check_bits(list(PRIVILEGES.values()))

PROFILE_VISIBILITY_ATTRS = ('profile_noindex', 'hide_from_lists', 'hide_from_search')

PUBLIC_NAME_MAX_SIZE = 64

QUARANTINE = timedelta(weeks=0)

RATE_LIMITS = {
    'add_email.source': (5, 60*60*24),  # 5 per day
    'add_email.target': (2, 60*60*24),  # 2 per day
    'admin.http-unsafe': (10, 60*60*24),  # 10 per day
    'change_currency': (4, 60*60*24*7),  # 4 per week
    'change_password': (7, 60*60*24*7),  # 7 per week
    'change_username': (7, 60*60*24*7),  # 7 per week
    'check_password': (25, 60*60*24*7),  # 25 per week
    'http-unsafe.ip-addr': (10, 10),  # 10 per 10 seconds
    'http-unsafe.user': (10, 10),  # 10 per 10 seconds
    'insert_identity': (7, 60*60*24*7),  # 7 per week
    'log-in.country': (10, 60),  # 10 per minute per country
    'log-in.email': (10, 60*60*24),  # 10 per day
    'log-in.email.not-verified': (2, 60*60*24),  # 2 per day
    'log-in.email.verified': (10, 60*60*24),  # 10 per day
    'log-in.ip-addr': (5, 5*60),  # 5 per 5 minutes per IP address
    'log-in.password': (3, 60*60),  # 3 per hour
    'make_team': (5, 60*60*24*7),  # 5 per week
    'refetch_elsewhere_data': (1, 60*60*24*7),  # retry after one week
    'refetch_repos': (1, 60*60*24),  # retry after one day
    'sign-up.ip-addr': (5, 60*60),  # 5 per hour per IP address
    'sign-up.ip-net': (15, 60*60),  # 15 per hour per IP network
    'sign-up.country': (5, 5*60),  # 5 per 5 minutes per country
    'sign-up.ip-version': (15, 5*60),  # 15 per 5 minutes per IP version
}

SESSION = 'session'
SESSION_REFRESH = timedelta(hours=1)
SESSION_TIMEOUT = timedelta(hours=6)


def make_standard_tip(label, weekly, currency):
    return StandardTip(
        label,
        Money(weekly, currency),
        Money(weekly / PERIOD_CONVERSION_RATES['monthly'], currency),
        Money(weekly / PERIOD_CONVERSION_RATES['yearly'], currency),
    )


class _StandardTips(defaultdict):
    def __missing__(self, currency):
        r = [
            make_standard_tip(
                label, convert_symbolic_amount(weekly, currency, rounding=ROUND_UP), currency
            ) for label, weekly in STANDARD_TIPS_EUR_USD
        ]
        self[currency] = r
        return r


STANDARD_TIPS_EUR_USD = (
    (_("Symbolic"), Decimal('0.01')),
    (_("Small"), Decimal('0.25')),
    (_("Medium"), Decimal('1.00')),
    (_("Large"), Decimal('5.00')),
    (_("Maximum"), DONATION_LIMITS_EUR_USD['weekly'][1]),
)
STANDARD_TIPS = _StandardTips(None, {
    'EUR': [make_standard_tip(label, weekly, 'EUR') for label, weekly in STANDARD_TIPS_EUR_USD],
    'USD': [make_standard_tip(label, weekly, 'USD') for label, weekly in STANDARD_TIPS_EUR_USD],
})

SUMMARY_MAX_SIZE = 100

TAKE_THROTTLING_THRESHOLD = MoneyAutoConvertDict(
    {k: Money('1.00', k) for k in ('EUR', 'USD')}
)

USERNAME_MAX_SIZE = 32
USERNAME_SUFFIX_BLACKLIST = set('.txt .html .htm .json .xml'.split())

del _
