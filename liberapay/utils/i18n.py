# encoding: utf8
from __future__ import print_function, unicode_literals

from collections import namedtuple, OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
from unicodedata import combining, normalize

from aspen.simplates.pagination import parse_specline, split_and_escape
from aspen.utils import utcnow
from babel.core import LOCALE_ALIASES, Locale
from babel.dates import format_datetime, format_timedelta
from babel.messages.extract import extract_python
from babel.messages.pofile import Catalog
from babel.numbers import (
    format_currency, format_decimal, format_number, format_percent,
    get_decimal_symbol, NumberFormatError, parse_decimal
)
import jinja2.ext

from liberapay.exceptions import InvalidNumber


Money = namedtuple('Money', 'amount currency')


class datedelta(timedelta):

    def __new__(cls, *a, **kw):
        if len(a) == 1 and not kw and isinstance(a[0], timedelta):
            return timedelta.__new__(cls, a[0].days, a[0].seconds, a[0].microseconds)
        return timedelta.__new__(cls, *a, **kw)


ALIASES = {k: v.lower() for k, v in LOCALE_ALIASES.items()}
ALIASES_R = {v: k for k, v in ALIASES.items()}


def strip_accents(s):
    return ''.join(c for c in normalize('NFKD', s) if not combining(c))


def make_sorted_dict(keys, d):
    items = ((k, d[k]) for k in keys)
    return OrderedDict(sorted(items, key=lambda t: strip_accents(t[1])))


COUNTRY_CODES = """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ
    BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR
    CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
    GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU
    ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ
    LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
    MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF
    PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI
    SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR
    TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
""".split()

COUNTRIES = make_sorted_dict(COUNTRY_CODES, Locale('en').territories)

LANGUAGE_CODES_2 = """
    aa af ak am ar as az be bg bm bn bo br bs ca cs cy da de dz ee el en eo es
    et eu fa ff fi fo fr ga gd gl gu gv ha he hi hr hu hy ia id ig ii is it ja
    ka ki kk kl km kn ko ks kw ky lg ln lo lt lu lv mg mk ml mn mr ms mt my nb
    nd ne nl nn nr om or os pa pl ps pt rm rn ro ru rw se sg si sk sl sn so sq
    sr ss st sv sw ta te tg th ti tn to tr ts uk ur uz ve vi vo xh yo zh zu
""".split()

LANGUAGES_2 = make_sorted_dict(LANGUAGE_CODES_2, Locale('en').languages)

LOCALES = {}
LOCALE_EN = LOCALES['en'] = Locale('en')
LOCALE_EN.catalog = Catalog('en')
LOCALE_EN.catalog.plural_func = lambda n: n != 1
LOCALE_EN.countries = COUNTRIES
LOCALE_EN.languages_2 = LANGUAGES_2


SEARCH_CONFS = dict((
    ('da', 'danish'),
    ('de', 'german'),
    ('en', 'english'),
    ('es', 'spanish'),
    ('fi', 'finnish'),
    ('fr', 'french'),
    ('hu', 'hungarian'),
    ('it', 'italian'),
    ('nb', 'norwegian'),
    ('nl', 'dutch'),
    ('nn', 'norwegian'),
    ('pt', 'portuguese'),
    ('ro', 'romanian'),
    ('ru', 'russian'),
    ('sv', 'swedish'),
    ('tr', 'turkish'),
))


_ = lambda a: a
HTTP_ERRORS = {
    403: _("Forbidden"),
    404: _("Not Found"),
    429: _("Too Many Requests"),
    500: _("Internal Server Error"),
    502: _("Upstream Error"),
}
del _


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


def i_format(loc, s, *a, **kw):
    if a:
        a = list(a)
    for c, f in [(a, enumerate), (kw, dict.items)]:
        for k, o in f(c):
            if isinstance(o, Decimal):
                c[k] = format_decimal(o, locale=loc)
            elif isinstance(o, int):
                c[k] = format_number(o, locale=loc)
            elif isinstance(o, Money):
                c[k] = format_money(*o, locale=loc)
            elif isinstance(o, datedelta):
                c[k] = format_timedelta(o, locale=loc, granularity='day')
            elif isinstance(o, timedelta):
                c[k] = format_timedelta(o, locale=loc)
            elif isinstance(o, datetime):
                c[k] = format_datetime(o, locale=loc)
    return s.format(*a, **kw)


def get_text(context, loc, s, *a, **kw):
    escape = context['escape']
    msg = loc.catalog.get(s)
    s2 = None
    if msg:
        s2 = msg.string
        if isinstance(s2, tuple):
            s2 = s2[0]
    if s2:
        s = s2
    else:
        loc = LOCALE_EN
    if a or kw:
        if isinstance(s, bytes):
            s = s.decode('ascii')
        return i_format(loc, escape(s), *a, **kw)
    return escape(s)


def n_get_text(tell_sentry, state, loc, s, p, n, *a, **kw):
    escape = state['escape']
    n = n or 0
    msg = loc.catalog.get((s, p))
    s2 = None
    if msg:
        try:
            s2 = msg.string[loc.catalog.plural_func(n)]
        except Exception as e:
            tell_sentry(e, state)
    if not s2:
        loc = LOCALE_EN
        s2 = s if n == 1 else p
    kw['n'] = format_number(n, locale=loc) or n
    if isinstance(s2, bytes):
        s2 = s2.decode('ascii')
    return i_format(loc, escape(s2), *a, **kw)


def to_age(dt):
    if isinstance(dt, datetime):
        return dt - utcnow()
    return datedelta(dt - date.today())


def regularize_locale(loc):
    if loc == 'no':

        # There are two forms of written Norwegian, Bokmål and Nynorsk, and
        # while ISO 639 includes `no` as a "macrolanguage", the CLDR (upon
        # which Babel, our i18n/l10n library, depends), does not include it at
        # all. Therefore, if a client sends `no` we interpret it as `nb_NO`.

        loc = 'nb_NO'
    return loc.replace('-', '_').lower()


def regularize_locales(locales):
    """Yield locale strings in the same format as they are in LOCALES.
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
    if 'en' not in locales_set and 'en_us' not in locales_set:
        yield 'en'
        yield 'en_us'


def parse_accept_lang(accept_lang):
    languages = (lang.split(";", 1)[0] for lang in accept_lang.split(","))
    return regularize_locales(languages)


def match_lang(languages):
    for lang in languages:
        loc = LOCALES.get(lang)
        if loc:
            return loc
    return LOCALE_EN


def format_money(number, currency, format=None, locale='en', trailing_zeroes=True):
    s = format_currency(number, currency, format, locale=locale)
    if not trailing_zeroes:
        s = s.replace(get_decimal_symbol(locale)+'00', '')
    return s


def get_lang_options(request, locale, previously_used_langs, add_multi=False):
    pref_langs = set(request.accept_langs + previously_used_langs)
    langs = OrderedDict()
    if add_multi:
        langs.update([('mul', locale.languages.get('mul', 'Multilingual'))])
    langs.update((k,v) for k, v in locale.languages_2.items() if k in pref_langs)
    langs.update([('', '---')])  # Separator
    langs.update(locale.languages_2)
    return langs


def set_up_i18n(website, request, state):
    accept_lang = request.headers.get("Accept-Language", "")
    langs = request.accept_langs = list(parse_accept_lang(accept_lang))
    loc = match_lang(langs)
    add_helpers_to_context(website.tell_sentry, state, loc)


def add_helpers_to_context(tell_sentry, context, loc):
    context['escape'] = lambda s: s  # to be overriden by renderers
    context['locale'] = loc
    context['decimal_symbol'] = get_decimal_symbol(locale=loc)
    context['_'] = lambda s, *a, **kw: get_text(context, loc, s, *a, **kw)
    context['ngettext'] = lambda *a, **kw: n_get_text(tell_sentry, context, loc, *a, **kw)
    context['Money'] = Money
    context['format_number'] = lambda *a: format_number(*a, locale=loc)
    context['format_decimal'] = lambda *a: format_decimal(*a, locale=loc)
    context['format_currency'] = lambda *a, **kw: format_money(*a, locale=loc, **kw)
    context['format_percent'] = lambda *a: format_percent(*a, locale=loc)
    context['format_datetime'] = lambda *a: format_datetime(*a, locale=loc)
    context['get_lang_options'] = lambda *a, **kw: get_lang_options(context['request'], loc, *a, **kw)
    context['to_age'] = to_age

    def parse_decimal_or_400(s, *a):
        try:
            return parse_decimal(s, *a, locale=loc)
        except (InvalidOperation, NumberFormatError, ValueError):
            raise InvalidNumber(s)

    context['parse_decimal'] = parse_decimal_or_400

    def to_age_str(o, **kw):
        if not isinstance(o, datetime):
            kw.setdefault('granularity', 'day')
        return format_timedelta(to_age(o), locale=loc, **kw)

    context['to_age_str'] = to_age_str

    def getdoc(name):
        versions = context['website'].docs[name]
        for lang in context['request'].accept_langs:
            doc = versions.get(lang)
            if doc:
                return doc
        return versions['en']

    context['getdoc'] = getdoc


def extract_spt(fileobj, *args, **kw):
    pages = list(split_and_escape(fileobj.read().decode('utf8')))
    npages = len(pages)
    for i, page in enumerate(pages, 1):
        f = BytesIO(b'\n' * page.offset + page.content.encode('utf8'))
        content_type, renderer = parse_specline(page.header)
        extractor = None
        if (i == npages and not page.header) or content_type in ('text/html', 'text/plain'):
            extractor = jinja2.ext.babel_extract
        elif i < 3:
            extractor = extract_python
        if extractor:
            for match in extractor(f, *args, **kw):
                yield match
