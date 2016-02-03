from __future__ import print_function, unicode_literals

from aspen.utils import utc
from collections import OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal
import re


_ = lambda a: a

ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                "-_")


BIRTHDAY = date(2015, 5, 22)

EMAIL_VERIFICATION_TIMEOUT = timedelta(hours=24)
EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')

JINJA_ENV_COMMON = dict(
    trim_blocks=True, lstrip_blocks=True,
    line_statement_prefix='%',
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
