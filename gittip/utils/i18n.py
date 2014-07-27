from __future__ import print_function, unicode_literals

import os

from aspen.utils import utcnow
from babel.dates import format_timedelta
import babel.messages.pofile
from babel.numbers import (
    format_currency, format_decimal, format_number, format_percent
)


def to_age(dt, loc):
    return format_timedelta(utcnow() - dt, add_direction=True, locale=loc)


def load_langs(localeDir):
    langs = {}
    for file in os.listdir(localeDir):
        parts = file.split(".")
        if len(parts) == 2 and parts[1] == "po":
            lang = parts[0]
            with open(os.path.join(localeDir, file)) as f:
                catalog = babel.messages.pofile.read_po(f)
                catalog_dict = {}
                for message in catalog:
                    if message.id:
                        catalog_dict[message.id] = message.string
                langs[lang] = catalog_dict
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
    request.context._ = lambda s: LANGS[loc].get(s, s) if loc in LANGS else s
    request.context.format_number = lambda *a: format_number(*a, locale=loc)
    request.context.format_decimal = lambda *a: format_decimal(*a, locale=loc)
    request.context.format_currency = lambda *a: format_currency(*a, locale=loc)
    request.context.format_percent = lambda *a: format_percent(*a, locale=loc)
    request.context.to_age = lambda delta: to_age(delta, loc)
