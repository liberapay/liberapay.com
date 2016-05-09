# coding: utf8
from __future__ import print_function, unicode_literals

from aspen.utils import utc
from collections import namedtuple, OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal
import re

from jinja2 import StrictUndefined


class CustomUndefined(StrictUndefined):
    __bool__ = __nonzero__ = lambda self: False

    def __str__(self):
        try:
            self._fail_with_undefined_error()
        except Exception as e:
            self._tell_sentry(e, {}, allow_reraise=True)
        return ''

    __unicode__ = __str__


Fees = namedtuple('Fees', ('var', 'fix'))


_ = lambda a: a

ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                "-_")

AVATAR_QUERY = '?s=160&default=retro'
AVATAR_SOURCES = 'libravatar bitbucket facebook github google twitter'.split()

BIRTHDAY = date(2015, 5, 22)

D_CENT = Decimal('0.01')
D_UNIT = Decimal('1.00')
D_ZERO = Decimal('0.00')

ELSEWHERE_ACTIONS = {'connect', 'lock', 'unlock'}

EMAIL_VERIFICATION_TIMEOUT = timedelta(hours=24)
EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')

EPOCH = datetime(1970, 1, 1, 0, 0, 0, 0, utc)

# https://www.mangopay.com/pricing/
FEE_PAYIN_BANK_WIRE = Fees(Decimal('0.005'), Decimal(0))  # 0.5%
FEE_PAYIN_CARD = Fees(Decimal('0.018'), Decimal('0.18'))  # 1.8% + €0.18
FEE_PAYOUT = Fees(Decimal(0), Decimal(0))
FEE_PAYOUT_OUTSIDE_SEPA = Fees(Decimal(0), Decimal('2.5'))
FEE_PAYOUT_WARN = Decimal('0.03')  # warn user when fee exceeds 3%
FEE_VAT = Decimal('0.17')  # 17% (Luxembourg rate)

JINJA_ENV_COMMON = dict(
    trim_blocks=True, lstrip_blocks=True,
    line_statement_prefix='%',
    #undefined=CustomUndefined,
)

# https://docs.mangopay.com/api-references/kyc-rules/
KYC_PAYIN_YEARLY_THRESHOLD = Decimal('2500')
KYC_PAYOUT_YEARLY_THRESHOLD = Decimal('1000')

LAUNCH_TIME = datetime(2016, 2, 3, 12, 50, 0, 0, utc)

MAX_TIP = Decimal('100.00')
MIN_TIP = Decimal('0.01')

PASSWORD_MIN_SIZE = 8
PASSWORD_MAX_SIZE = 150

PAYIN_CARD_MIN = Decimal("15.00")  # fee ≈ 3.5%
PAYIN_CARD_TARGET = Decimal("92.00")  # fee ≈ 2.33%

PRIVACY_FIELDS = OrderedDict([
    ('hide_giving', _("Hide total giving from others.")),
    ('hide_receiving', _("Hide total receiving from others.")),
    ('hide_from_search', _("Hide myself from search results.")),
])
PRIVACY_FIELDS_S = ' '.join(PRIVACY_FIELDS.keys())

QUARANTINE = timedelta(weeks=4)

SEPA_ZONE = set("""
    AT BE BG CH CY CZ DE DK EE ES ES FI FR GB GI GR HR HU IE IS IT LI LT LU LV
    MC MT NL NO PL PT RO SE SI SK
""".split())

SESSION = b'session'
SESSION_REFRESH = timedelta(hours=1)
SESSION_TIMEOUT = timedelta(hours=6)

STANDARD_TIPS = (
    (_("Symbolic ({0})"), Decimal('0.01')),
    (_("Small ({0})"), Decimal('0.25')),
    (_("Medium ({0})"), Decimal('1.00')),
    (_("Large ({0})"), Decimal('5.00')),
    (_("Maximum ({0})"), MAX_TIP),
)

USERNAME_MAX_SIZE = 32

del _
