from collections import defaultdict, namedtuple
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, ROUND_UP
import re

from babel.numbers import get_currency_precision
from markupsafe import Markup
from pando.utils import utc

from .i18n.currencies import D_CENT, D_ZERO, D_MAX, Money  # noqa: F401


def ordered_set(keys):
    return dict.fromkeys(keys)


def check_bits(bits):
    assert len(set(bits)) == len(bits)  # no duplicates
    assert not [b for b in bits if '{0:b}'.format(b).count('1') != 1]  # single bit


Event = namedtuple('Event', 'name bit title')


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
    from liberapay.website import website
    rate = website.currency_exchange_rates[('EUR', target_currency)]
    minimum = Money.MINIMUMS[target_currency].amount
    return max(
        to_precision(amount * rate, precision, rounding).quantize(minimum, rounding),
        minimum
    )


class MoneyAutoConvertDict(defaultdict):

    def __init__(self, *args, precision=2):
        super().__init__(None, *args)
        self.precision = precision

    def __missing__(self, currency):
        r = Money(
            convert_symbolic_amount(self['EUR'].amount, currency, self.precision),
            currency
        )
        self[currency] = r
        return r


StandardTip = namedtuple('StandardTip', 'label weekly monthly yearly')


_ = lambda a: a

ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                "-_.")

AVATAR_QUERY = '?s=160&d=404'
AVATAR_SOURCES = (
    'libravatar bitbucket github gitlab mastodon pleroma twitch twitter'
).split()

BASE64URL_CHARS = set('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_')

BIRTHDAY = date(2015, 5, 22)

CARD_BRANDS = {
    'amex': 'American Express',
    'diners': 'Diners Club',
    'discover': 'Discover',
    'jcb': 'JCB',
    'mastercard': 'Mastercard',
    'unionpay': 'UnionPay',
    'visa': 'Visa',
    'unknown': '',
}

CURRENCIES = ordered_set([
    'EUR', 'USD',
    'AUD', 'BGN', 'BRL', 'CAD', 'CHF', 'CNY', 'CZK', 'DKK', 'GBP', 'HKD', 'HRK',
    'HUF', 'IDR', 'ILS', 'INR', 'ISK', 'JPY', 'KRW', 'MXN', 'MYR', 'NOK', 'NZD',
    'PHP', 'PLN', 'RON', 'RUB', 'SEK', 'SGD', 'THB', 'TRY', 'ZAR'
])

class _DonationLimits(defaultdict):
    def __missing__(self, currency):
        minimum = Money.MINIMUMS[currency].amount
        eur_weekly_amounts = DONATION_LIMITS_EUR_USD['weekly']
        converted_weekly_amounts = (
            convert_symbolic_amount(eur_weekly_amounts[0], currency),
            convert_symbolic_amount(eur_weekly_amounts[1], currency)
        )
        r = {
            'weekly': tuple(Money(x, currency) for x in converted_weekly_amounts),
            'monthly': tuple(
                Money((x * Decimal(52) / Decimal(12)).quantize(minimum, rounding=ROUND_UP), currency)
                for x in converted_weekly_amounts
            ),
            'yearly': tuple(Money(x * Decimal(52), currency) for x in converted_weekly_amounts),
        }
        self[currency] = r
        return r

DONATION_LIMITS_WEEKLY_EUR_USD = (Decimal('0.01'), Decimal('100.00'))
DONATION_LIMITS_EUR_USD = {
    'weekly': DONATION_LIMITS_WEEKLY_EUR_USD,
    'monthly': tuple((x * Decimal(52) / Decimal(12)).quantize(D_CENT, rounding=ROUND_UP)
                     for x in DONATION_LIMITS_WEEKLY_EUR_USD),
    'yearly': tuple(x * Decimal(52) for x in DONATION_LIMITS_WEEKLY_EUR_USD),
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
    # This was the regexp used by MangoPay as of February 2017.
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
    Event('pledgee_joined', 16, _("When someone I pledge to joins Liberapay")),
    Event('team_invite', 32, _("When someone invites me to join a team")),
    Event('payin_failed', 2**11, _("When a payment I initiated fails")),
    Event('payin_succeeded', 2**12, _("When a payment I initiated succeeds")),
    Event('payin_refund_initiated', 2**13, _("When money is being refunded back to me")),
    Event('upcoming_debit', 2**14, _("When an automatic donation renewal payment is upcoming")),
    Event('missing_route', 2**15, _("When I no longer have any valid payment instrument")),
    Event('renewal_aborted', 2**16, _("When a donation renewal payment has been aborted")),
]
check_bits([e.bit for e in EVENTS])
EVENTS = {e.name: e for e in EVENTS}
EVENTS_S = ' '.join(EVENTS.keys())

HTML_A = Markup('<a href="%s">%s</a>')

IDENTITY_FIELDS = set("""
    birthdate headquarters_address name nationality occupation organization_name
    postal_address
""".split())

INVOICE_DOC_MAX_SIZE = 5000000
INVOICE_DOCS_EXTS = ['pdf', 'jpeg', 'jpg', 'png']
INVOICE_DOCS_LIMIT = 25

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

LAUNCH_TIME = datetime(2016, 2, 3, 12, 50, 0, 0, utc)

PARTICIPANT_KINDS = {
    'individual': _("Individual"),
    'organization': _("Organization"),
    'group': _("Team"),
}

PASSWORD_MIN_SIZE = 8
PASSWORD_MAX_SIZE = 150

PAYIN_AMOUNTS = {
    'paypal': {
        'min_acceptable': MoneyAutoConvertDict({  # fee > 10%
            'EUR': Money('2.00', 'EUR'),
            'USD': Money('2.00', 'USD'),
        }),
        'min_recommended': MoneyAutoConvertDict({  # fee < 8%
            'EUR': Money('10.00', 'EUR'),
            'USD': Money('12.00', 'USD'),
        }),
        'low_fee': MoneyAutoConvertDict({  # fee < 6%
            'EUR': Money('40.00', 'EUR'),
            'USD': Money('48.00', 'USD'),
        }),
        'max_acceptable': {
            'new_donor': MoneyAutoConvertDict({
                'EUR': Money('5200.00', 'EUR'),
                'USD': Money('5200.00', 'USD'),
            }),
            'active_donor': MoneyAutoConvertDict({
                'EUR': Money('12000.00', 'EUR'),
                'USD': Money('12000.00', 'USD'),
            }),
            'trusted_donor': MoneyAutoConvertDict({
                'EUR': Money('52000.00', 'EUR'),
                'USD': Money('52000.00', 'USD'),
            }),
        },
    },
    'stripe': {
        'min_acceptable': MoneyAutoConvertDict({  # fee > 10%
            'EUR': Money('2.00', 'EUR'),
            'USD': Money('2.00', 'USD'),
        }),
        'min_recommended': MoneyAutoConvertDict({  # fee < 8%
            'EUR': Money('10.00', 'EUR'),
            'USD': Money('12.00', 'USD'),
        }),
        'low_fee': MoneyAutoConvertDict({  # fee < 6%
            'EUR': Money('40.00', 'EUR'),
            'USD': Money('48.00', 'USD'),
        }),
        'max_acceptable': {
            'new_donor': MoneyAutoConvertDict({
                'EUR': Money('5200.00', 'EUR'),
                'USD': Money('5200.00', 'USD'),
            }),
            'active_donor': MoneyAutoConvertDict({
                'EUR': Money('12000.00', 'EUR'),
                'USD': Money('12000.00', 'USD'),
            }),
            'trusted_donor': MoneyAutoConvertDict({
                'EUR': Money('52000.00', 'EUR'),
                'USD': Money('52000.00', 'USD'),
            }),
            # Stripe has per-account limits for SEPA Direct Debits. Liberapay's
            # account has a per-debit limit of €75k, and no weekly limit.
        },
    },
}

PAYIN_SETTLEMENT_DELAYS = {
    'stripe-sdd': timedelta(days=6),
}

PAYMENT_METHODS = {
    'paypal': "PayPal",
    'stripe-card': _("Credit/Debit Card"),
    'stripe-sdd': _("Direct Debit"),
}

PAYOUT_COUNTRIES = {
    'paypal': set("""
        AD AE AG AI AL AM AN AO AR AT AU AW AZ BA BB BE BF BG BH BI BJ BM BN BO
        BR BS BT BW BY BZ C2 CA CD CG CH CI CK CL CM CO CR CV CY CZ DE DJ DK DM
        DO DZ EC EE EG ER ES ET FI FJ FK FM FO FR GA GD GE GF GI GL GM GN GP GR
        GT GW GY HK HN HR HU ID IE IL IN IS IT JM JO JP KE KG KH KI KM KN KR KW
        KY KZ LA LC LI LK LS LT LU LV MA MC MD ME MG MH MK ML MN MQ MR MS MT MU
        MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PL
        PM PN PT PW PY QA RE RO RS RW SA SB SC SE SG SH SI SJ SK SL SM SN SO SR
        ST SV SZ TC TD TG TH TJ TM TN TO TT TT TT TT TV TW TZ UA UG GB US UY VA
        VC VE VG VN VU WF WS YE YT ZA ZM ZW
        PR
    """.split()),  # https://www.paypal.com/us/webapps/mpp/country-worldwide

    'stripe': set("""
        AT AU BE BG CA CH CY CZ DE DK EE ES FI FR GB GI GR HK HR HU IE IT JP LI
        LT LU LV MT MX MY NL NO NZ PL PT RO SE SG SI SK US
        PR
    """.split()),  # https://stripe.com/global
}

# https://developer.paypal.com/docs/api/reference/currency-codes/
PAYPAL_CURRENCIES = set("""
    AUD CAD CHF CZK DKK EUR GBP HKD HUF ILS JPY MXN NOK NZD PHP PLN RUB SEK SGD
    THB TWD USD
""".split())

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

POSTAL_ADDRESS_KEYS_LIBERAPAY = (
    'country', 'region', 'city', 'postal_code', 'local_address'
)

PRIVACY_FIELDS = {
    'hide_giving': (_("Do not publish the amounts of money I send."), False),
    'hide_receiving': (_("Do not publish the amounts of money I receive."), False),
    'hide_from_search': (_("Hide this profile from search results on Liberapay."), True),
    'profile_noindex': (_("Tell web search engines not to index this profile."), True),
    'hide_from_lists': (_("Prevent this profile from being listed on Liberapay."), True),
}
PRIVACY_FIELDS_S = ' '.join(PRIVACY_FIELDS.keys())

PRIVILEGES = dict(admin=1, run_payday=2)
check_bits(list(PRIVILEGES.values()))

PUBLIC_NAME_MAX_SIZE = 64

RATE_LIMITS = {
    'add_email.source': (5, 60*60*24),  # 5 per day
    'add_email.target': (2, 60*60*24),  # 2 per day
    'admin.http-unsafe': (10, 60*60*24),  # 10 per day
    'change_currency': (4, 60*60*24*7),  # 4 per week
    'change_password': (7, 60*60*24*7),  # 7 per week
    'change_username': (7, 60*60*24*7),  # 7 per week
    'check_password': (25, 60*60*24*7),  # 25 per week
    'elsewhere-lookup.ip-addr': (5, 20),  # 5 per 20 seconds
    'email.bypass_error': (2, 60*60*24*7),  # 2 per week
    'email.unblacklist.source': (5, 60*60*24*7),  # 5 per week
    'email.unblacklist.target': (3, 60*60*24*7),  # 3 per week
    'hash_password.ip-addr': (3, 15),  # 3 per 15 seconds
    'http-query.ip-addr': (10, 10),  # 10 per 10 seconds
    'http-query.user': (10, 10),  # 10 per 10 seconds
    'http-unsafe.ip-addr': (10, 10),  # 10 per 10 seconds
    'http-unsafe.user': (10, 10),  # 10 per 10 seconds
    'insert_identity': (7, 60*60*24*7),  # 7 per week
    'log-in.email': (10, 60*60*24),  # 10 per day
    'log-in.email.ip-addr': (5, 60*60),  # 5 per hour per IP address
    'log-in.email.ip-net': (10, 30*60),  # 10 per 30 minutes per IP network
    'log-in.email.country': (15, 15*60),  # 15 per 15 minutes per country
    'log-in.email.not-verified': (2, 60*60*24),  # 2 per day
    'log-in.email.verified': (10, 60*60*24),  # 10 per day
    'log-in.password': (3, 60*60),  # 3 per hour
    'log-in.password.ip-addr': (3, 60*60),  # 3 per hour per IP address
    'make_team': (5, 60*60*24*7),  # 5 per week
    'payin.from-user': (15, 60*60*24*7),  # 15 per week
    'payin.from-ip-addr': (15, 60*60*24*7),  # 15 per week
    'refetch_elsewhere_data': (1, 60*60*24*7),  # retry after one week
    'refetch_repos': (1, 60*60*24),  # retry after one day
    'sign-up.email': (1, 5*60),  # this is used to detect near-simultaneous requests,
                                 # so 5 minutes should be plenty enough
    'sign-up.ip-addr': (5, 60*60),  # 5 per hour per IP address
    'sign-up.ip-net': (10, 30*60),  # 10 per 30 minutes per IP network
    'sign-up.country': (15, 15*60),  # 15 per 15 minutes per country
    'sign-up.ip-version': (20, 10*60),  # 20 per 10 minutes per IP version
}

SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}

SESSION = 'session'
SESSION_REFRESH = timedelta(hours=12)
SESSION_TIMEOUT = timedelta(hours=6)


def make_standard_tip(label, weekly, currency):
    precision = get_currency_precision(currency)
    minimum = D_CENT if precision == 2 else Decimal(10) ** (-precision)
    return StandardTip(
        label,
        Money(weekly, currency),
        Money((weekly / PERIOD_CONVERSION_RATES['monthly']).quantize(minimum), currency),
        Money((weekly / PERIOD_CONVERSION_RATES['yearly']).quantize(minimum), currency),
    )


class _StandardTips(defaultdict):
    def __missing__(self, currency):
        r = [
            make_standard_tip(
                label, convert_symbolic_amount(weekly, currency), currency
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
FEEDBACK_MAX_SIZE = 1000

TAKE_THROTTLING_THRESHOLD = MoneyAutoConvertDict(
    {k: Money('1.00', k) for k in ('EUR', 'USD')}
)

USERNAME_MAX_SIZE = 32
USERNAME_SUFFIX_BLACKLIST = set('.txt .html .htm .json .xml'.split())

del _
