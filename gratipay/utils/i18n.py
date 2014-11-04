# encoding: utf8
from __future__ import print_function, unicode_literals

from io import BytesIO
import re
from unicodedata import combining, normalize

from aspen.resources.pagination import parse_specline, split_and_escape
from aspen.utils import utcnow
from babel.core import LOCALE_ALIASES
from babel.dates import format_timedelta
from babel.messages.extract import extract_python
from babel.numbers import (
    format_currency, format_decimal, format_number, format_percent,
    get_decimal_symbol, parse_decimal
)
import jinja2.ext


ALIASES = {k: v.lower() for k, v in LOCALE_ALIASES.items()}
ALIASES_R = {v: k for k, v in ALIASES.items()}


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
    msg = loc.catalog.get(s)
    if msg:
        s = msg.string or s
    if a or kw:
        if isinstance(s, bytes):
            s = s.decode('ascii')
        return s.format(*a, **kw)
    return s


def n_get_text(website, request, loc, s, p, n, *a, **kw):
    n = n or 0
    msg = loc.catalog.get((s, p))
    s2 = None
    if msg:
        try:
            s2 = msg.string[loc.catalog.plural_func(n)]
        except Exception as e:
            website.tell_sentry(e, request)
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
    if loc == 'no':

        # There are two forms of written Norwegian, Bokmål and Nynorsk, and
        # while ISO 639 includes `no` as a "macrolanguage", the CLDR (upon
        # which Babel, our i18n/l10n library, depends), does not include it at
        # all. Therefore, if a client sends `no` we interpret it as `nb_NO`.

        loc = 'nb_NO'
    return loc.replace('-', '_').lower()


def regularize_locales(locales):
    """Yield locale strings in the same format as they are in website.locales.
    """
    locales = [regularize_locale(loc) for loc in locales]
    locales_set = set(locales)
    for loc in locales:
        yield loc
        parts = loc.split('_')
        if len(parts) > 1 and parts[0] not in locales_set:
            # Insert "fr" after "fr_fr" if it's not somewhere in the list
            yield parts[0]
        alias = ALIASES.get(loc)
        if alias and alias not in locales_set:
            # Insert "fr_fr" after "fr" if it's not somewhere in the list
            yield alias


def strip_accents(s):
    return ''.join(c for c in normalize('NFKD', s) if not combining(c))


def get_locale_for_request(request, website):
    accept_lang = request.headers.get("Accept-Language", "")
    languages = (lang.split(";", 1)[0] for lang in accept_lang.split(","))
    languages = request.accept_langs = regularize_locales(languages)
    for lang in languages:
        loc = website.locales.get(lang)
        if loc:
            return loc
    return website.locale_en


def format_currency_with_options(number, currency, locale='en', trailing_zeroes=True):
    s = format_currency(number, currency, locale=locale)
    if not trailing_zeroes:
        s = s.replace(get_decimal_symbol(locale)+'00', '')
    return s


def add_helpers_to_context(website, request):
    context = request.context
    loc = context['locale'] = get_locale_for_request(request, website)
    context['decimal_symbol'] = get_decimal_symbol(locale=loc)
    context['_'] = lambda s, *a, **kw: get_text(request, loc, s, *a, **kw)
    context['ngettext'] = lambda *a, **kw: n_get_text(website, request, loc, *a, **kw)
    context['format_number'] = lambda *a: format_number(*a, locale=loc)
    context['format_decimal'] = lambda *a: format_decimal(*a, locale=loc)
    context['format_currency'] = lambda *a, **kw: format_currency_with_options(*a, locale=loc, **kw)
    context['format_percent'] = lambda *a: format_percent(*a, locale=loc)
    context['parse_decimal'] = lambda *a: parse_decimal(*a, locale=loc)
    def _to_age(delta):
        try:
            return to_age(delta, loc)
        except:
            return to_age(delta, 'en')
    context['to_age'] = _to_age


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
