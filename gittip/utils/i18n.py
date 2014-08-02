from __future__ import print_function, unicode_literals

import os
import re

from aspen.utils import utcnow
from babel.dates import format_timedelta
import babel.messages.pofile
from babel.numbers import (
    format_currency, format_decimal, format_number, format_percent
)


ternary_re = re.compile(r' *(.*) *\? *(.*) *: *(.*) *')
and_re = re.compile(r' *&& *')
or_re = re.compile(r' *\|\| *')


def get_function_from_rule(rule):
    oldrule = None
    while oldrule != rule:
        oldrule = rule
        rule = ternary_re.sub(r'(\2) if \1 else (\3)', rule)
    rule = and_re.sub(' and ', rule)
    rule = or_re.sub(' or ', rule)
    return eval('lambda n: ' + rule, {'__builtins__': {}})


def get_text(request, loc, s, *a, **kw):
    catalog = LANGS.get(loc)
    msg = catalog.get(s) if catalog else None
    if isinstance(s, tuple):
        n = kw.pop('n', None)
        if n is None:
            try:
                raise TypeError('n should not be None')
            except Exception as e:
                request.website.tell_sentry(e, request)
        s2 = None
        if msg:
            try:
                s2 = msg.string[catalog.plural_func(n)]
            except Exception as e:
                request.website.tell_sentry(e, request)
        if s2 is None:
            loc = 'en'
            s2 = s[n != 1]
        kw['n'] = n and format_number(n, locale=loc) or '{n}'
        s = s2
    elif msg:
        s = msg.string
    if a or kw:
        return s.format(*a, **kw)
    return s


def to_age(dt, loc):
    return format_timedelta(dt - utcnow(), add_direction=True, locale=loc)


def load_langs(localeDir):
    langs = {}
    for file in os.listdir(localeDir):
        parts = file.split(".")
        if len(parts) == 2 and parts[1] == "po":
            lang = parts[0]
            with open(os.path.join(localeDir, file)) as f:
                c = langs[lang] = babel.messages.pofile.read_po(f)
                c.plural_func = get_function_from_rule(c.plural_expr)
    return langs


LANGS = load_langs("i18n")


def get_locale_for_request(request):
    accept_lang = request.headers.get("Accept-Language", "")
    languages = (lang.split(";", 1)[0] for lang in accept_lang.split(","))
    for loc in languages:
        if loc.startswith("en") or LANGS.has_key(loc):
            return loc
    return "en"


def inbound(request):
    context = request.context
    loc = context.locale = get_locale_for_request(request)
    context._ = lambda s, *a, **kw: get_text(request, loc, s, *a, **kw)
    context.format_number = lambda *a: format_number(*a, locale=loc)
    context.format_decimal = lambda *a: format_decimal(*a, locale=loc)
    context.format_currency = lambda *a: format_currency(*a, locale=loc)
    context.format_percent = lambda *a: format_percent(*a, locale=loc)
    def _to_age(delta):
        try:
            return to_age(delta, loc)
        except:
            return to_age(delta, 'en')
    context.to_age = _to_age
