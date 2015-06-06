from __future__ import print_function, unicode_literals

from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal
import re


ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                "-_")


BIRTHDAY = date(2015, 5, 22)

EMAIL_VERIFICATION_TIMEOUT = timedelta(hours=24)
EMAIL_RE = re.compile(r'^[^@]+@[^@]+\.[^@]+$')

MAX_TIP = Decimal('100.00')
MIN_TIP = Decimal('0.01')

PASSWORD_MIN_SIZE = 8
PASSWORD_MAX_SIZE = 150

_ = lambda a: a
PRIVACY_FIELDS = OrderedDict([
    ('hide_giving', _("Hide total giving from others.")),
    ('hide_receiving', _("Hide total receiving from others.")),
    ('hide_from_search', _("Hide myself from search results.")),
])
del _
PRIVACY_FIELDS_S = ' '.join(PRIVACY_FIELDS.keys())

SESSION = b'session'
SESSION_REFRESH = timedelta(hours=1)
SESSION_TIMEOUT = timedelta(hours=6)

USERNAME_MAX_SIZE = 32
