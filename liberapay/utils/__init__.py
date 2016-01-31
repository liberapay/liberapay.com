# encoding: utf8

from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import date, datetime, timedelta
import re

from aspen import Response, json
from aspen.utils import to_rfc822, utcnow
from markupsafe import Markup
from postgres.cursors import SimpleCursorBase

import liberapay
from liberapay.exceptions import AuthRequired


BEGINNING_OF_EPOCH = to_rfc822(datetime(1970, 1, 1)).encode('ascii')


def get_participant(state, restrict=True, redirect_stub=True, allow_member=False):
    """Given a Request, raise Response or return Participant.

    If restrict is True then we'll restrict access to owners and admins.

    """
    request = state['request']
    user = state['user']
    slug = request.line.uri.path['username']
    _ = state['_']

    if restrict and user.ANON:
        raise AuthRequired

    if slug.startswith('~'):
        thing = 'id'
        value = slug[1:]
        participant = user if user and str(user.id) == value else None
    else:
        thing = 'lower(username)'
        value = slug.lower()
        participant = user if user and user.username.lower() == value else None

    if participant is None:
        from liberapay.models.participant import Participant  # avoid circular import
        participant = Participant._from_thing(thing, value) if value else None
        if participant is None or participant.kind == 'community':
            raise Response(404)

    if request.method in ('GET', 'HEAD'):
        if slug != participant.username:
            canon = '/' + participant.username + request.line.uri[len(slug)+1:]
            raise Response(302, headers={'Location': canon})

    status = participant.status
    if status == 'closed':
        if user.is_admin:
            return participant
        raise Response(410)
    elif status == 'stub':
        if redirect_stub:
            to = participant.resolve_stub()
            assert to
            raise Response(302, headers={'Location': to})

    if restrict:
        if participant != user:
            if allow_member and participant.kind == 'group' and user.member_of(participant):
                pass
            elif not user.is_admin:
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


def excerpt_intro(text, length=175, append='…'):
    if not text:
        return ''
    if len(text) > length:
        return text[:length] + append
    return text


def is_card_expired(exp_year, exp_month):
    today = date.today()
    cur_year, cur_month = today.year, today.month
    return exp_year < cur_year or exp_year == cur_year and exp_month < cur_month


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


svg_attrs_re = re.compile(r'\s+(?:height|width|x|y|xmlns)=(["\']).*?\1')

def include_svg(svg, height, width, x=None, y=None):
    """For when you want to include an SVG in an HTML page or in another SVG.
    """
    assert svg.startswith('<svg')
    i = svg.find('>')
    assert i != -1
    d = locals()
    attrs = svg_attrs_re.sub('', svg[4:i])
    for a in ('height', 'width', 'x', 'y'):
        v = d[a]
        if v is None:
            continue
        attrs += ' %s="%s"' % (a, v)
    return Markup(svg[:4] + attrs + svg[i:])


def group_by(iterable, key):
    r = {}
    for obj in iterable:
        try:
            k = obj[key]
        except KeyError:
            continue
        r.setdefault(k, []).append(obj)
    return r
