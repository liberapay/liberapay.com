# coding: utf8
from __future__ import print_function, unicode_literals

from aspen.utils import utc
from collections import OrderedDict
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


_ = lambda a: a

ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                "-_")

AVATAR_QUERY = '?s=160&default=retro'

BALANCE_MAX = Decimal("1000")

BIRTHDAY = date(2015, 5, 22)

CHARGE_MIN = Decimal("15.00")  # fee ≈ 3%
CHARGE_TARGET = Decimal("92.00")  # fee ≈ 2%

EMAIL_VERIFICATION_TIMEOUT = timedelta(hours=24)
EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')

EPOCH = datetime(1970, 1, 1, 0, 0, 0, 0, utc)

# https://www.mangopay.com/pricing/
FEE_CHARGE_FIX = Decimal('0.18')  # 0.18 euros
FEE_CHARGE_VAR = Decimal('0.018')  # 1.8%
FEE_CREDIT = 0
FEE_CREDIT_OUTSIDE_SEPA = Decimal("2.5")

JINJA_ENV_COMMON = dict(
    trim_blocks=True, lstrip_blocks=True,
    line_statement_prefix='%',
    #undefined=CustomUndefined,
)

LAUNCH_TIME = datetime(2016, 2, 3, 12, 50, 0, 0, utc)

MAX_TIP = Decimal('100.00')
MIN_TIP = Decimal('0.01')

QUARANTINE = timedelta(weeks=4)

PASSWORD_MIN_SIZE = 8
PASSWORD_MAX_SIZE = 150

PRIVACY_FIELDS = OrderedDict([
    ('hide_giving', _("Hide total giving from others.")),
    ('hide_receiving', _("Hide total receiving from others.")),
    ('hide_from_search', _("Hide myself from search results.")),
])
PRIVACY_FIELDS_S = ' '.join(PRIVACY_FIELDS.keys())

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
)

USERNAME_MAX_SIZE = 32

del _
