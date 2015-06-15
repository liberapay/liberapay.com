# encoding: utf8

from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime, timedelta

from aspen import Response, json
from aspen.utils import to_rfc822, utcnow
from postgres.cursors import SimpleCursorBase

import liberapay


BEGINNING_OF_EPOCH = to_rfc822(datetime(1970, 1, 1)).encode('ascii')

# Difference between current time and credit card expiring date when
# card is considered as expiring
EXPIRING_DELTA = timedelta(days = 30)


def dict_to_querystring(mapping):
    if not mapping:
        return u''

    arguments = []
    for key, values in mapping.iteritems():
        for val in values:
            arguments.append(u'='.join([key, val]))

    return u'?' + u'&'.join(arguments)


def canonicalize(path, base, canonical, given, arguments=None):
    if given != canonical:
        assert canonical.lower() == given.lower()  # sanity check
        remainder = path[len(base + given):]

        if arguments is not None:
            arguments = dict_to_querystring(arguments)

        newpath = base + canonical + remainder + arguments or ''
        raise Response(302, headers={"Location": newpath})


def get_participant(state, restrict=True, redirect_stub=True):
    """Given a Request, raise Response or return Participant.

    If restrict is True then we'll restrict access to owners and admins.

    """
    request = state['request']
    user = state['user']
    slug = request.line.uri.path['username']
    qs = request.line.uri.querystring
    _ = state['_']

    if restrict:
        if user.ANON:
            raise Response(403, _("You need to log in to access this page."))

    from liberapay.models.participant import Participant  # avoid circular import
    if isinstance(user, Participant) and user.username.lower() == slug.lower():
        participant = user
    else:
        participant = Participant.from_username(slug)

    if participant is None:
        raise Response(404)

    canonicalize(request.line.uri.path.raw, '/', participant.username, slug, qs)

    status = participant.status
    if status == 'closed':
        if user.is_admin:
            return participant
        raise Response(410)
    elif status == 'stub':
        if redirect_stub:
            to = participant.resolve_stub()
            assert to
            request.redirect(to)

    if restrict:
        if participant != user:
            if not user.is_admin:
                raise Response(403, _("You are not authorized to access this page."))

    return participant


def update_global_stats(website):
    stats = website.db.one("""
        SELECT nactive, transfer_volume FROM paydays
        ORDER BY ts_end DESC LIMIT 1
    """, default=(0, 0.0))
    website.gnactive = stats[0]
    website.gtransfer_volume = stats[1]


def _execute(this, sql, params=[]):
    print(sql.strip(), params)
    super(SimpleCursorBase, this).execute(sql, params)

def log_cursor(f):
    "Prints sql and params to stdout. Works globaly so watch for threaded use."
    def wrapper(*a, **kw):
        try:
            SimpleCursorBase.execute = _execute
            ret = f(*a, **kw)
        finally:
            del SimpleCursorBase.execute
        return ret
    return wrapper


def excerpt_intro(text, length=175, append=u'…'):
    if not text:
        return ''
    if len(text) > length:
        return text[:length] + append
    return text


def is_card_expiring(expiration_year, expiration_month):
    now = datetime.utcnow()
    expiring_date = datetime(expiration_year, expiration_month, 1)
    delta = expiring_date - now
    return delta < EXPIRING_DELTA


def set_cookie(cookies, key, value, expires=None, httponly=True, path=b'/'):
    cookies[key] = value
    cookie = cookies[key]
    if expires:
        if isinstance(expires, timedelta):
            expires += utcnow()
        if isinstance(expires, datetime):
            expires = to_rfc822(expires).encode('ascii')
        cookie[b'expires'] = expires
    if httponly:
        cookie[b'httponly'] = True
    if path:
        cookie[b'path'] = path
    if liberapay.canonical_scheme == 'https':
        cookie[b'secure'] = True


def erase_cookie(cookies, key, **kw):
    set_cookie(cookies, key, '', BEGINNING_OF_EPOCH, **kw)


def filter_profile_subnav(user, participant, pages):
    out = []
    for foo, bar, show_them, show_others in pages:
        if (user == participant and show_them) \
        or (user != participant and show_others) \
        or user.is_admin:
            out.append((foo, bar))
    return out


def to_javascript(obj):
    """For when you want to inject an object into a <script> tag.
    """
    return json.dumps(obj).replace('</', '<\\/')
