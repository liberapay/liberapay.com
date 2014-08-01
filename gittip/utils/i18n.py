from __future__ import print_function, unicode_literals

import os

from aspen.utils import utcnow
from babel.dates import format_timedelta
import babel.messages.pofile
from babel.numbers import (
    format_currency, format_decimal, format_number, format_percent
)
import re


def get_function_from_rule(rule):
    oldrule = None
    while oldrule != rule:
        oldrule = rule
        rule = re.sub('(.*)\?(.*):(.*)', r'(\1) and (\2) or (\3)', oldrule)
    rule = re.sub('&&', 'and', rule)
    rule = re.sub('\|\|', 'or', rule)
    return eval('lambda n: ' + rule)


def get_text(s, loc, count=0):
    if loc in LANGS:
        new_s = LANGS[loc].get(s)
        s = new_s.string if new_s else s
    if isinstance(s, tuple):
        try:
            plural_fn = get_function_from_rule(LANGS[loc].plural_expr)
            i = int(plural_fn(count))
            s = s[i] if len(s) >= i + 1 else s[0]
        except:
            return s[0]
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
                langs[lang] = babel.messages.pofile.read_po(f)
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
    loc = request.context.locale = get_locale_for_request(request)
    request.context._ = lambda s, count=0: get_text(s, loc, count=count)
    request.context.format_number = lambda *a: format_number(*a, locale=loc)
    request.context.format_decimal = lambda *a: format_decimal(*a, locale=loc)
    request.context.format_currency = lambda *a: format_currency(*a, locale=loc)
    request.context.format_percent = lambda *a: format_percent(*a, locale=loc)
    def _to_age(delta):
        try:
            return to_age(delta, loc)
        except:
            return to_age(delta, 'en')
    request.context.to_age = _to_age
