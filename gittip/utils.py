import math
import datetime

from aspen.utils import typecheck
from aspen._tornado.escape import linkify


def wrap(u):
    """Given a unicode, return a unicode.
    """
    typecheck(u, unicode)
    u = linkify(u)  # Do this first, because it calls xthml_escape.
    u = u.replace(u'\r\n', u'<br />\r\n').replace(u'\n', u'<br />\n')
    return u if u else '...'


def commaize(n, places=1):
    """Given a number, return a string with commas and a decimal -- 1,000.0.
    """
    out = ("%%.0%df" % places) % n
    try:
        whole, fraction = out.split('.')
    except ValueError:
        whole, fraction = (out, '')
    _whole = []
    for i, digit in enumerate(reversed(whole), start=1):
        _whole.insert(0, digit)
        if i % 3 == 0:
            _whole.insert(0, ',')
    out = ''.join(_whole + ['.', fraction]).lstrip(',').rstrip('.')
    return out


def total_seconds(td):
    """
    Python 2.7 adds a total_seconds method to timedelta objects.
    See http://docs.python.org/library/datetime.html#datetime.timedelta.total_seconds

    This function is taken from https://bitbucket.org/jaraco/jaraco.compat/src/e5806e6c1bcb/py26compat/__init__.py#cl-26

    """
    try:
        result = td.total_seconds()
    except AttributeError:
        result = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6
    return result


def dt2age(dt):
    """Given a Unix timestamp (UTC) or a datetime object, return an age string
    relative to now.

        range                                       denomination    example
        ======================================================================
        0-1 second                                 "just a moment"
        1-59 seconds                                seconds         13 seconds
        60 sec - 59 min                             minutes         13 minutes
        60 min - 23 hrs, 59 min                     hours           13 hours
        24 hrs - 13 days, 23 hrs, 59 min            days            13 days
        14 days - 27 days, 23 hrs, 59 min           weeks           3 weeks
        28 days - 12 months, 31 days, 23 hrs, 59 mn months          6 months
        1 year -                                    years           1 year

    We'll go up to years for now.

    Times in the future are indicated by "in (denomination)" and times
    already passed are indicated by "(denomination) ago".

    """

    if not isinstance(dt, datetime.datetime):
        dt = datetime.datetime.utcfromtimestamp(dt)


    # Define some helpful constants.
    # ==============================

    sec =   1
    min =  60 * sec
    hr  =  60 * min
    day =  24 * hr
    wk  =   7 * day
    mn  =   4 * wk
    yr  = 365 * day


    # Get the raw age in seconds.
    # ===========================

    now = datetime.datetime.now(dt.tzinfo)
    age = total_seconds(abs(now - dt))


    # Convert it to a string.
    # =======================
    # We start with the coarsest unit and filter to the finest. Pluralization 
    # is centralized.

    if age < 1:
        return 'just a moment ago'

    elif age >= yr:         # years
        amount = age / yr
        unit = 'year'
    elif age >= mn:         # months
        amount = age / mn
        unit = 'month'
    elif age >= (2 * wk):   # weeks
        amount = age / wk
        unit = 'week'
    elif age >= day:        # days
        amount = age / day
        unit = 'day'
    elif age >= hr:         # hours
        amount = age / hr
        unit = 'hour'
    elif age >= min:        # minutes
        amount = age / min
        unit = 'minute'
    else:                   # seconds
        amount = age
        unit = 'second'


    # Pluralize and return.
    # =====================

    amount = int(math.floor(amount))
    if amount != 1:
        unit += 's'
    if amount < 10:
        amount = ['zero', 'a', 'two', 'three', 'four', 'five', 'six', 
                  'seven', 'eight', 'nine'][amount]
    age = ' '.join([str(amount), unit])
    fmt = 'in {age}' if dt > now else '{age} ago'
    return fmt.format(age=age)
