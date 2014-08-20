from __future__ import print_function, unicode_literals

from io import BytesIO
import os
import re

from aspen.resources.pagination import parse_specline, split_and_escape
from aspen.utils import utcnow
from babel.core import Locale
from babel.dates import format_timedelta
import babel.messages.pofile
from babel.messages.extract import extract_python
from babel.numbers import (
    format_currency, format_decimal, format_number, format_percent, parse_decimal, get_decimal_symbol
)
import jinja2.ext


# Monkey-patch Babel
Locale('fr').currency_symbols['USD'] = '$'


ternary_re = re.compile(r'^\(? *(.+?) *\? *(.+?) *: *(.+?) *\)?$')
and_re = re.compile(r' *&& *')
or_re = re.compile(r' *\|\| *')


def ternary_sub(m):
    g1, g2, g3 = m.groups()
    return '%s if %s else %s' % (g2, g1, ternary_re.sub(ternary_sub, g3))


def get_function_from_rule(rule):
    rule = ternary_re.sub(ternary_sub, rule.strip())
    rule = and_re.sub(' and ', rule)
    rule = or_re.sub(' or ', rule)
    return eval('lambda n: ' + rule, {'__builtins__': {}})


def get_text(request, loc, s, *a, **kw):
    catalog = LANGS.get(loc)
    msg = catalog.get(s) if catalog else None
    if msg:
        s = msg.string or s
    if a or kw:
        if isinstance(s, bytes):
            s = s.decode('ascii')
        return s.format(*a, **kw)
    return s


def n_get_text(request, loc, s, p, n, *a, **kw):
    n = n or 0
    catalog = LANGS.get(loc)
    msg = catalog.get((s, p)) if catalog else None
    s2 = None
    if msg:
        try:
            s2 = msg.string[catalog.plural_func(n)]
        except Exception as e:
            request.website.tell_sentry(e, request)
    if s2 is None:
        loc = 'en'
        s2 = s if n == 1 else p
    kw['n'] = format_number(n, locale=loc) or n
    if isinstance(s2, bytes):
        s2 = s2.decode('ascii')
    return s2.format(*a, **kw)


def to_age(dt, loc):
    return format_timedelta(dt - utcnow(), add_direction=True, locale=loc)


def regularize_locale(loc):
    return loc.split('-', 1)[0].lower()


def load_langs(localeDir):
    langs = {}
    for file in os.listdir(localeDir):
        parts = file.split(".")
        if len(parts) == 2 and parts[1] == "po":
            lang = regularize_locale(parts[0])
            with open(os.path.join(localeDir, file)) as f:
                c = langs[lang] = babel.messages.pofile.read_po(f)
                c.plural_func = get_function_from_rule(c.plural_expr)
    return langs


LANGS = load_langs("i18n")


def get_locale_for_request(request):
    accept_lang = request.headers.get("Accept-Language", "")
    languages = (lang.split(";", 1)[0] for lang in accept_lang.split(","))
    for loc in languages:
        loc = regularize_locale(loc)
        if loc == "en" or loc in LANGS:
            return loc
    return "en"


def _format_currency(loc, dsym, amount, currency):
    return format_currency(amount, currency, locale=loc).replace(dsym+'00', '')


def inbound(request):
    context = request.context
    loc = context.locale = get_locale_for_request(request)
    dsym = context.decimal_symbol = get_decimal_symbol(locale=loc)
    context._ = lambda s, *a, **kw: get_text(request, loc, s, *a, **kw)
    context.ngettext = lambda *a, **kw: n_get_text(request, loc, *a, **kw)
    context.format_number = lambda *a: format_number(*a, locale=loc)
    context.format_decimal = lambda *a: format_decimal(*a, locale=loc)
    context.format_currency = lambda *a: _format_currency(loc, dsym, *a)
    context.format_percent = lambda *a: format_percent(*a, locale=loc)
    context.parse_decimal = lambda *a: parse_decimal(*a, locale=loc)
    def _to_age(delta):
        try:
            return to_age(delta, loc)
        except:
            return to_age(delta, 'en')
    context.to_age = _to_age


def extract_spt(fileobj, *args, **kw):
    pages = list(split_and_escape(fileobj.read()))
    npages = len(pages)
    for i, page in enumerate(pages, 1):
        f = BytesIO(b'\n' * page.offset + page.content)
        content_type, renderer = parse_specline(page.header)
        extractor = None
        if (i == npages and not page.header) or content_type == 'text/html' or renderer == 'jinja2':
            extractor = jinja2.ext.babel_extract
        elif i < 3:
            extractor = extract_python
        if extractor:
            for match in extractor(f, *args, **kw):
                yield match
