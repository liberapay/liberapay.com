# encoding: utf8
from __future__ import print_function, unicode_literals

from collections import namedtuple, OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import md5
from io import BytesIO
import re
from unicodedata import combining, normalize

from six import text_type

from aspen.simplates.pagination import parse_specline, split_and_escape
import babel.core
from babel.dates import format_date, format_datetime, format_timedelta
from babel.messages.extract import extract_python
from babel.messages.pofile import Catalog
from babel.numbers import (
    format_currency, format_decimal, format_number, format_percent,
    NumberFormatError, parse_decimal
)
import jinja2.ext
from mangopay.utils import Money
from markupsafe import Markup
from pando.utils import utcnow

from liberapay.constants import CURRENCIES
from liberapay.exceptions import InvalidNumber
from liberapay.utils.currencies import MoneyBasket
from liberapay.website import website


def LegacyMoney(o):
    return o if isinstance(o, (Money, MoneyBasket)) else Money(o, 'EUR')


Wrap = namedtuple('Wrap', 'value wrapper')


BOLD = Markup('<b>%s</b>')


def Bold(value):
    return Wrap(value, BOLD)


class Currency(str):
    pass


class Age(timedelta):

    def __new__(cls, *a, **kw):
        if len(a) == 1 and not kw and isinstance(a[0], timedelta):
            return timedelta.__new__(cls, a[0].days, a[0].seconds, a[0].microseconds)
        return timedelta.__new__(cls, *a, **kw)


class Locale(babel.core.Locale):

    def __init__(self, *a, **kw):
        super(Locale, self).__init__(*a, **kw)
        self.decimal_symbol = self.number_symbols.get('decimal', '.')
        delta_p = self.currency_formats['standard'].pattern
        assert ';' not in delta_p
        self.currency_delta_pattern = '+{0};-{0}'.format(delta_p)

    def format_money(self, m, format=None, trailing_zeroes=True):
        s = format_currency(m.amount, m.currency, format, locale=self)
        if not trailing_zeroes:
            s = s.replace(self.decimal_symbol + '00', '')
        return s

    def format_date(self, date, format='medium'):
        if format.endswith('_yearless'):
            format = self.date_formats[format]
        return format_date(date, format, locale=self)

    def format_datetime(self, *a):
        return format_datetime(*a, locale=self)

    def format_decimal(self, *a):
        return format_decimal(*a, locale=self)

    def format_list(self, l):
        n = len(l)
        if n > 2:
            last = n - 2
            r = l[0]
            for i, item in enumerate(l[1:]):
                r = self.list_patterns[
                    'start' if i == 0 else 'end' if i == last else 'middle'
                ].format(r, item)
            return r
        elif n == 2:
            return self.list_patterns['2'].format(*l)
        else:
            return l[0] if n == 1 else None

    def format_money_basket(self, basket, sep=','):
        if basket is None:
            return '0'
        items = (
            format_currency(money.amount, money.currency, locale=self)
            for money in basket if money
        )
        if sep == ',':
            r = self.format_list(list(items))
        else:
            r = sep.join(items)
        return r or '0'

    def format_money_delta(self, money, *a):
        return format_currency(
            money.amount, money.currency, *a,
            format=self.currency_delta_pattern, locale=self
        )

    def format_number(self, *a):
        return format_number(*a, locale=self)

    def format_percent(self, *a):
        return format_percent(*a, locale=self)

    def parse_decimal_or_400(self, s, *a):
        try:
            return parse_decimal(s, *a, locale=self)
        except (InvalidOperation, NumberFormatError, ValueError):
            raise InvalidNumber(s)

    @staticmethod
    def title(s):
        return s[0].upper() + s[1:] if s and s[0].islower() else s

    def to_age_str(self, o, **kw):
        if not isinstance(o, datetime):
            kw.setdefault('granularity', 'day')
        return format_timedelta(to_age(o), locale=self, **kw)


ALIASES = {k: v.lower() for k, v in babel.core.LOCALE_ALIASES.items()}
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

CURRENCIES_MAP = {
    k: v[-1][0]
    for k, v in babel.core.get_global('territory_currencies').items()
    if v[-1][0] in CURRENCIES
}

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
    503: _("Service Unavailable"),
    504: _("Gateway Timeout"),
}
del _


ternary_re = re.compile(r'^(.+?) *\? *(.+?) *: *(.+?)$')
and_re = re.compile(r' *&& *')
or_re = re.compile(r' *\|\| *')


def strip_parentheses(s):
    s = s.strip()
    if s[:1] == '(' and s[-1:] == ')':
        s = s[1:-1].strip()
    return s


def ternary_sub(m):
    g1, g2, g3 = m.groups()
    return '%s if %s else %s' % (g2, g1, ternary_re.sub(ternary_sub, strip_parentheses(g3)))


def get_function_from_rule(rule):
    rule = ternary_re.sub(ternary_sub, strip_parentheses(rule))
    rule = and_re.sub(' and ', rule)
    rule = or_re.sub(' or ', rule)
    return eval('lambda n: ' + rule, {'__builtins__': {}})


def _decode(o):
    return o.decode('ascii') if isinstance(o, bytes) else o


def i_format(loc, s, *a, **kw):
    if a:
        a = list(a)
    for c, f in [(a, enumerate), (kw, dict.items)]:
        for k, o in f(c):
            o, wrapper = (o.value, o.wrapper) if isinstance(o, Wrap) else (o, None)
            if isinstance(o, text_type):
                pass
            elif isinstance(o, Decimal):
                c[k] = format_decimal(o, locale=loc)
            elif isinstance(o, int):
                c[k] = format_number(o, locale=loc)
            elif isinstance(o, Money):
                c[k] = loc.format_money(o)
            elif isinstance(o, MoneyBasket):
                c[k] = loc.format_money_basket(o)
            elif isinstance(o, Age):
                c[k] = format_timedelta(o, locale=loc, **o.format_args)
            elif isinstance(o, timedelta):
                c[k] = format_timedelta(o, locale=loc)
            elif isinstance(o, datetime):
                c[k] = format_datetime(o, locale=loc)
            elif isinstance(o, date):
                c[k] = format_date(o, locale=loc)
            elif isinstance(o, Locale):
                c[k] = loc.languages.get(o.language) or o.language.upper()
            elif isinstance(o, Currency):
                c[k] = loc.currencies.get(o, o)
            if wrapper:
                c[k] = wrapper % (c[k],)
    return s.format(*a, **kw)


def get_text(state, loc, s, *a, **kw):
    escape = state['escape']
    msg = loc.catalog.get(s)
    s2 = None
    if msg:
        s2 = msg.string
        if isinstance(s2, tuple):
            s2 = s2[0]
    if not s2:
        s2 = s
        if loc != LOCALE_EN:
            loc = LOCALE_EN
            state['partial_translation'] = True
    if a or kw:
        try:
            return i_format(loc, escape(_decode(s2)), *a, **kw)
        except Exception as e:
            website.tell_sentry(e, state)
            return i_format(LOCALE_EN, escape(_decode(s)), *a, **kw)
    return escape(s2)


def n_get_text(state, loc, s, p, n, *a, **kw):
    escape = state['escape']
    n, wrapper = (n.value, n.wrapper) if isinstance(n, Wrap) else (n, None)
    n = n or 0
    msg = loc.catalog.get((s, p) if s else p)
    s2 = None
    if msg:
        try:
            s2 = msg.string[loc.catalog.plural_func(n)]
        except Exception as e:
            website.tell_sentry(e, state)
    if not s2:
        s2 = s if n == 1 else p
        if loc != LOCALE_EN:
            loc = LOCALE_EN
            state['partial_translation'] = True
    kw['n'] = format_number(n, locale=loc) or n
    if wrapper:
        kw['n'] = wrapper % kw['n']
    try:
        return i_format(loc, escape(_decode(s2)), *a, **kw)
    except Exception as e:
        website.tell_sentry(e, state)
        return i_format(LOCALE_EN, escape(_decode(s if n == 1 else p)), *a, **kw)


def getdoc(state, name):
    versions = state['website'].docs[name]
    for lang in state['request'].accept_langs:
        doc = versions.get(lang)
        if doc:
            return doc
    return versions['en']


def to_age(dt, **kw):
    if isinstance(dt, datetime):
        delta = Age(dt - utcnow())
    else:
        delta = Age(dt - date.today())
        kw.setdefault('granularity', 'day')
    delta.format_args = kw
    return delta


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


def get_lang_options(request, locale, previously_used_langs, add_multi=False):
    pref_langs = set(request.accept_langs + previously_used_langs)
    langs = OrderedDict()
    if add_multi:
        langs.update([('mul', locale.languages.get('mul', 'Multilingual'))])
    langs.update((k, v) for k, v in locale.languages_2.items() if k in pref_langs)
    langs.update([('', '---')])  # Separator
    langs.update(locale.languages_2)
    return langs


def set_up_i18n(website, request, state):
    accept_lang = request.headers.get(b"Accept-Language", b"").decode('ascii', 'replace')
    langs = request.accept_langs = list(parse_accept_lang(accept_lang))
    loc = match_lang(langs)
    add_helpers_to_context(state, loc)


def _return_(a):
    return a


def add_helpers_to_context(context, loc):
    context.update(
        escape=_return_,  # to be overriden by renderers
        locale=loc,
        Bold=Bold,
        Currency=Currency,
        Money=Money,
        to_age=to_age,
        _=lambda s, *a, **kw: get_text(context, kw.pop('loc', loc), s, *a, **kw),
        ngettext=lambda *a, **kw: n_get_text(context, kw.pop('loc', loc), *a, **kw),
        format_date=loc.format_date,
        format_datetime=loc.format_datetime,
        format_decimal=loc.format_decimal,
        format_list=loc.format_list,
        format_money=loc.format_money,
        format_money_delta=loc.format_money_delta,
        format_number=loc.format_number,
        format_percent=loc.format_percent,
        parse_decimal=loc.parse_decimal_or_400,
        to_age_str=loc.to_age_str,
    )


def add_currency_to_state(request, user):
    qs_currency = request.qs.get('currency')
    if qs_currency in CURRENCIES:
        return {'currency': qs_currency}
    cookie = request.headers.cookie.get(str('currency'))
    if cookie and cookie.value in CURRENCIES:
        return {'currency': cookie.value}
    if user:
        return {'currency': user.main_currency}
    else:
        return {'currency': CURRENCIES_MAP.get(request.country) or 'EUR'}


def extract_custom(extractor, *args, **kw):
    for match in extractor(*args, **kw):
        msg = match[2]
        if isinstance(msg, tuple) and msg[0] == '':
            unused = "<unused singular (hash=%s)>" % md5(msg[1]).hexdigest()
            msg = (unused, msg[1], msg[2])
            match = (match[0], match[1], msg, match[3])
        yield match


def extract_jinja2_custom(*args, **kw):
    return extract_custom(jinja2.ext.babel_extract, *args, **kw)


def extract_python_custom(*args, **kw):
    return extract_custom(extract_python, *args, **kw)


def extract_spt(fileobj, *args, **kw):
    pages = list(split_and_escape(fileobj.read().decode('utf8')))
    npages = len(pages)
    for i, page in enumerate(pages, 1):
        f = BytesIO(b'\n' * page.offset + page.content.encode('utf8'))
        content_type, renderer = parse_specline(page.header)
        extractor = None
        python_page = i < 3 and i < npages and not page.header
        json_page = renderer in ('json_dump', 'jsonp_dump')
        if python_page or json_page:
            extractor = extract_python_custom
        else:
            extractor = extract_jinja2_custom
        if extractor:
            for match in extractor(f, *args, **kw):
                yield match


if __name__ == '__main__':
    import sys

    from babel.messages.pofile import read_po, write_po

    if sys.argv[1] == 'po-reflag':
        # This adds the `python-brace-format` flag to messages that contain braces
        # https://github.com/python-babel/babel/issues/333
        pot_path = sys.argv[2]
        print('rewriting PO template file', pot_path)
        # read PO file
        with open(pot_path, 'rb') as pot:
            catalog = read_po(pot)
        # tweak message flags
        for m in catalog:
            msg = m.id
            contains_brace = any(
                '{' in s for s in (msg if isinstance(msg, tuple) else (msg,))
            )
            if contains_brace:
                m.flags.add('python-brace-format')
            m.flags.discard('python-format')
        # write back
        with open(pot_path, 'wb') as pot:
            write_po(pot, catalog, width=0)

    else:
        print("unknown command")
        raise SystemExit(1)
