"""This is the Python library behind www.gittip.com.
"""
import datetime
import locale
import os
from decimal import Decimal

import aspen


try:  # XXX This can't be right.
    locale.setlocale(locale.LC_ALL, "en_US.utf8")
except locale.Error:
    import sys
    if sys.platform == 'win32':
        locale.setlocale(locale.LC_ALL, '')
    else:
        locale.setlocale(locale.LC_ALL, "en_US.UTF-8")


BIRTHDAY = datetime.date(2012, 6, 1)
CARDINALS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
             'eight', 'nine']
ORDINALS = ['zeroth', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth',
            'seventh', 'eighth', 'ninth', 'tenth']
MONTHS = [None, 'January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']

def age():
    today = datetime.date.today()
    nmonths = (12 - BIRTHDAY.month) \
            + (12 * (today.year - BIRTHDAY.year - 1)) \
            + (today.month)
    plural = 's' if nmonths != 1 else ''
    if nmonths < 10:
        nmonths = CARDINALS[nmonths]
    else:
        nmonths = str(nmonths)
    return "%s month%s" % (nmonths, plural)


class NotSane(Exception):
    """This is used when a sanity check fails.

    A sanity check is when it really seems like the logic shouldn't allow the
    condition to arise, but you never know.

    """

db = None # This global is wired in wireup. It's an instance of
          # gittip.postgres.PostgresManager.


MAX_TIP = Decimal('100.00')
MIN_TIP = Decimal('0.00')

RESTRICTED_IDS = None


def log(*messages, **kw):
    if 'level' not in kw:
        kw['level'] = 2
    aspen.log(*messages, **kw)


# canonizer
# =========
# This is an Aspen hook to ensure that requests are served on a certain root
# URL, even if multiple domains point to the application.

class X: pass
canonical_scheme = None
canonical_host = None

def canonize(request):
    """Enforce a certain scheme and hostname. Store these on request as well.
    """
    scheme = request.headers.get('X-Forwarded-Proto', 'http') # per Heroku
    host = request.headers['Host']
    bad_scheme = scheme != canonical_scheme
    bad_host = bool(canonical_host) and (host != canonical_host)
                # '' and False => ''
    if bad_scheme or bad_host:
        url = '%s://%s' % (canonical_scheme, canonical_host)
        if request.line.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            # Redirect to a particular path for idempotent methods.
            url += request.line.uri.path.raw
            if request.line.uri.querystring:
                url += '?' + request.line.uri.querystring.raw
        else:
            # For non-idempotent methods, redirect to homepage.
            url += '/'
        request.redirect(url)


def configure_payments(request):
    # Work-around for https://github.com/balanced/balanced-python/issues/5
    import balanced
    balanced.configure(os.environ['BALANCED_API_SECRET'])
