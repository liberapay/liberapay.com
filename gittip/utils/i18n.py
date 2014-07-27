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

def parse_locales(request):
    accept_lang = request.headers.get("Accept-Language", "")
    locales = []
    for lang in accept_lang.split(","):
        lang_parts = lang.split(";")
        locales.append(lang_parts[0])
    return locales

def parse_locale(request):
    for loc in parse_locales(request):
        if loc.startswith("en") or LANGS.has_key(loc):
            return loc
    return "en"

def _(s, loc):
    if not LANGS.has_key(loc):
        return s
    return LANGS[loc].get(s, s)
