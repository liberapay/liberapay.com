from __future__ import print_function, unicode_literals

from datetime import datetime
import os

from babel.dates import format_timedelta
import babel.messages.pofile


def to_age(dt, loc):
    return format_timedelta(datetime.now().replace(tzinfo=dt.tzinfo) - dt, locale=loc)


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


def parse_locale(request):
    accept_lang = request.headers.get("Accept-Language", "")
    languages = (lang.split(";", 1)[0] for lang in accept_lang.split(","))
    for loc in languages:
        if loc.startswith("en") or LANGS.has_key(loc):
            return loc
    return "en"


def _(s, loc):
    return LANGS[loc].get(s, s) if loc in LANGS else s
