from collections import namedtuple
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from sys import intern
from unicodedata import combining, normalize
import warnings

import babel.core
from babel.dates import format_date, format_datetime, format_time, format_timedelta
from babel.messages.pofile import Catalog
from babel.numbers import parse_pattern
from cached_property import cached_property
from markupsafe import Markup
import opencc
from pando.utils import utcnow

from ..exceptions import AmbiguousNumber, InvalidNumber
from ..website import website
from .currencies import (
    CURRENCIES, CURRENCY_REPLACEMENTS, D_MAX, Money, MoneyBasket, to_precision,
)


MONEY_AMOUNT_FORMAT = parse_pattern('#,##0.00')
ONLY_ZERO = {'0'}


def _return_(a):
    return a


def LegacyMoney(o):
    return o if isinstance(o, (Money, MoneyBasket)) else Money(o, 'EUR')


Wrap = namedtuple('Wrap', 'value wrapper')


BOLD = Markup('<b>%s</b>')


def Bold(value):
    return Wrap(value, BOLD)


class Country(str):
    __slots__ = ()


class Currency(str):
    __slots__ = ()


class Language(str):
    __slots__ = ()


class List(list):
    __slots__ = ('pattern',)

    def __init__(self, iterable, pattern='standard'):
        list.__init__(self, iterable)
        self.pattern = pattern


class Month(int):
    __slots__ = ()


class Percent:
    __slots__ = ('number', 'min_precision', 'group_separator')

    def __init__(self, number, min_precision=1, group_separator=True):
        self.number = number
        self.min_precision = min_precision
        self.group_separator = group_separator


class Year(int):
    __slots__ = ()


class Age(timedelta):

    __slots__ = ('format_args',)

    def __new__(cls, *a, **kw):
        format_args = kw.pop('format_args', {})
        if len(a) == 1 and not kw and isinstance(a[0], timedelta):
            r = timedelta.__new__(cls, a[0].days, a[0].seconds, a[0].microseconds)
        else:
            r = timedelta.__new__(cls, *a, **kw)
        r.format_args = format_args
        return r


class Locale(babel.core.Locale):

    Age = Age
    Country = Country
    Currency = Currency
    Language = Language
    List = List
    Month = Month
    Percent = Percent
    Year = Year

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.currency_formats['amount_only'] = MONEY_AMOUNT_FORMAT
        delta_p = self.currency_formats['standard'].pattern
        minus_sign = self.number_symbols[self.default_numbering_system].get('minusSign', '-')
        plus_sign = self.number_symbols[self.default_numbering_system].get('plusSign', '+')
        if ';' in delta_p:
            pos, neg = delta_p.split(';')
            assert len(neg) >= len(pos), (self, neg, pos)
            neg = neg.replace('-', minus_sign)
            assert minus_sign in neg, (self, neg, minus_sign)
            pos = neg.replace(minus_sign, plus_sign)
            self.currency_delta_pattern = parse_pattern('%s;%s' % (pos, neg))
        else:
            self.currency_delta_pattern = parse_pattern(
                '{0}{2};{1}{2}'.format(plus_sign, minus_sign, delta_p)
            )

    def _(self, state, s, *a, **kw):
        escape = state['escape']
        msg = self.catalog._messages.get(s)
        s2 = None
        if msg:
            s2 = msg.string
            if isinstance(s2, tuple):
                s2 = s2[0]
            if msg.fuzzy:
                state['fuzzy_translation'] = True
        if not s2:
            s2 = s
            if self.language != 'en':
                self = LOCALE_EN
                state['partial_translation'] = True
        if a or kw:
            try:
                return self.format(escape(s2), *a, **kw)
            except Exception as e:
                website.tell_sentry(e)
                return LOCALE_EN.format(escape(s), *a, **kw)
        return escape(s2)

    def ngettext(self, state, s, p, n, *a, **kw):
        if n == 1 and not s:
            warnings.warn(f"missing singular | {p}")
        escape = state['escape']
        n, wrapper = (n.value, n.wrapper) if isinstance(n, Wrap) else (n, None)
        n = n or 0
        msg = self.catalog._messages.get(s if s else p)
        s2 = None
        if msg:
            try:
                s2 = msg.string[self.catalog.plural_func(n)]
            except Exception as e:
                website.tell_sentry(e)
            if s2:
                if msg.fuzzy:
                    state['fuzzy_translation'] = True
            else:
                n_placeholders = p.count('{')
                s2 = next((
                    x for x in msg.string if x and x.count('{') == n_placeholders
                ), None)
                if s2:
                    state['partial_translation'] = True
        if not s2:
            s2 = s if n == 1 else p
            if self.language != 'en':
                self = LOCALE_EN
                state['partial_translation'] = True
        kw['n'] = self.format_decimal(n) or n
        if wrapper:
            kw['n'] = wrapper % kw['n']
        try:
            return self.format(escape(s2), *a, **kw)
        except Exception as e:
            website.tell_sentry(e)
            return LOCALE_EN.format(escape(s if n == 1 else p), *a, **kw)

    def format(self, s, *a, **kw):
        if a:
            a = list(a)
        for c, f in [(a, enumerate), (kw, dict.items)]:
            for k, o in f(c):
                o, wrapper = (o.value, o.wrapper) if isinstance(o, Wrap) else (o, None)
                if isinstance(o, str):
                    if isinstance(o, Country):
                        o = self.countries.get(o, o)
                    elif isinstance(o, Currency):
                        o = self.currencies.get(o, o)
                    elif isinstance(o, Language):
                        o = self.languages.get(o) or o.upper()
                elif isinstance(o, (Decimal, int)):
                    if isinstance(o, Month):
                        o = self.months['stand-alone']['wide'][o]
                    elif isinstance(o, Year):
                        o = str(o)
                    else:
                        o = self.format_decimal(o)
                elif isinstance(o, Money):
                    o = self.format_money(o)
                elif isinstance(o, MoneyBasket):
                    o = self.format_money_basket(o)
                elif isinstance(o, Percent):
                    o = self.format_percent(
                        o.number,
                        min_precision=o.min_precision,
                        group_separator=o.group_separator,
                    )
                elif isinstance(o, timedelta):
                    o = self.format_timedelta(o)
                elif isinstance(o, date):
                    if isinstance(o, datetime):
                        o = format_datetime(o, locale=self)
                    else:
                        o = format_date(o, locale=self)
                elif isinstance(o, Locale):
                    o = self.languages.get(o.language) or o.language.upper()
                elif isinstance(o, list):
                    escape = getattr(s.__class__, 'escape', _return_)
                    pattern = getattr(o, 'pattern', 'standard')
                    o = self.format_list(o, pattern, escape)
                if wrapper:
                    c[k] = wrapper % (o,)
                elif o is not c[k]:
                    c[k] = o
        return s.format(*a, **kw)

    def format_money(self, m, format='standard', trailing_zeroes=True):
        s = self.currency_formats[format].apply(
            m.amount, self, currency=m.currency, currency_digits=True,
            decimal_quantization=True, numbering_system='default',
        )
        if trailing_zeroes is False:
            i = s.find(self.number_symbols[self.default_numbering_system]['decimal'])
            if i != -1 and set(s[i+1:]) == ONLY_ZERO:
                s = s[:i]
        return s

    def format_date(self, date, format='medium'):
        if format.endswith('_yearless'):
            format = self.date_formats[format]
        return format_date(date, format, locale=self)

    def format_datetime(self, *a):
        return format_datetime(*a, locale=self)

    def format_decimal(self, number, **kw):
        kw.setdefault('numbering_system', 'default')
        return self.decimal_formats[None].apply(number, self, **kw)

    def format_list(self, l, pattern='standard', escape=_return_):
        n = len(l)
        if n > 2:
            last = n - 2
            r = l[0]
            for i, item in enumerate(l[1:]):
                r = self.format(escape(self.list_patterns[pattern][
                    'start' if i == 0 else 'end' if i == last else 'middle'
                ]), r, item)
            return r
        elif n == 2:
            return self.format(escape(self.list_patterns[pattern]['2']), *l)
        else:
            return self.format(escape('{0}'), l[0]) if n == 1 else None

    def format_money_basket(self, basket, sep=','):
        if basket is None:
            return '0'
        pattern = self.currency_formats['standard']
        items = (
            pattern.apply(
                money.amount, self, currency=money.currency,
                numbering_system='default',
            )
            for money in basket if money
        )
        if sep == ',':
            r = self.format_list(list(items))
        else:
            r = sep.join(items)
        return r or '0'

    def format_money_delta(self, money):
        return self.currency_delta_pattern.apply(
            money.amount, self, currency=money.currency, currency_digits=True,
            decimal_quantization=True, numbering_system='default',
        )

    def format_percent(self, number, min_precision=1, group_separator=True):
        decimal_quantization = True
        if number < 1 and min_precision > 0:
            number = to_precision(Decimal(str(number)), min_precision)
            decimal_quantization = False
        return self.percent_formats[None].apply(
            number, self,
            decimal_quantization=decimal_quantization,
            group_separator=True, numbering_system='default',
        )

    def format_time(self, t, format='medium'):
        return format_time(t, format=format, locale=self)

    def format_timedelta(self, o, **kw):
        if type(o) is Age:
            kw.update(o.format_args)
        return format_timedelta(o, locale=self, **kw)

    def parse_money_amount(self, string, currency, maximum=D_MAX):
        group_symbol = self.number_symbols[self.default_numbering_system]['group']
        decimal_symbol = self.number_symbols[self.default_numbering_system]['decimal']
        # Strip the string of spaces, and of the specified currency's symbol in
        # this locale (if that symbol exists).
        string = string.strip()
        currency_symbol = self.currency_symbols.get(currency)
        if currency_symbol:
            symbol_length = len(currency_symbol)
            if string.startswith(currency_symbol):
                string = string[symbol_length:]
            elif string.endswith(currency_symbol):
                string = string[:-symbol_length]
            string = string.strip()
        # Parse the number. If the string contains unexpected characters,
        # then an `InvalidNumber` exception is raised.
        try:
            decimal = Decimal(
                ''.join(string.split()).replace(decimal_symbol, '.')
                if group_symbol.isspace() else
                string.replace(group_symbol, '').replace(decimal_symbol, '.')
            )
        except (InvalidOperation, ValueError):
            raise InvalidNumber(string)
        # Check that the input isn't ambiguous.
        # https://github.com/liberapay/liberapay.com/issues/1066
        if group_symbol in string:
            proper = self.format_decimal(decimal, decimal_quantization=False)
            ambiguous = string != proper and (
                (string + ('' if decimal_symbol in string else decimal_symbol)).rstrip('0') !=
                (proper + ('' if decimal_symbol in proper else decimal_symbol)).rstrip('0')
            )
            if ambiguous:
                # Irregular number format (e.g. `10.00` in German)
                try:
                    proper_alt = (
                        string.replace(decimal_symbol, '').replace(group_symbol, '.')
                    )
                except (InvalidOperation, ValueError):
                    raise AmbiguousNumber(string, [proper])
                else:
                    raise AmbiguousNumber(string, [proper_alt, proper])
        # Check that the amount is within the acceptable range.
        if maximum is not None and decimal > maximum:
            raise InvalidNumber(string)
        money = Money(decimal, currency).round_down()
        if money.amount != decimal:
            # The input amount exceeds maximum precision (e.g. $0.001).
            raise InvalidNumber(string)
        return money

    @cached_property
    def global_tag(self):
        "The BCP47 tag for this locale, in lowercase, without the territory."
        return intern('-'.join(filter(None, (self.language, self.script))).lower())

    @cached_property
    def tag(self):
        "The BCP47 tag for this locale, in lowercase."
        return intern(
            '-'.join(filter(None, (self.language, self.script, self.territory))).lower()
        )

    @staticmethod
    def title(s):
        return s[0].upper() + s[1:] if s and s[0].islower() else s


LOCALE_EN = Locale('en')


def strip_accents(s):
    return ''.join(c for c in normalize('NFKD', s) if not combining(c))


def make_sorted_dict(keys, d, d2={}, clean=_return_):
    items = ((k, clean(d.get(k) or d2[k])) for k in keys)
    return dict(sorted(items, key=lambda t: strip_accents(t[1])))


# Some languages have multiple written forms in widespread use. In particular,
# Chinese has two main character sets (Traditional and Simplified), and we use
# the OpenCC library to convert from one to the other.
CONVERTERS = {
    'zh-hans': {
        'zh-hant': opencc.OpenCC('s2t.json').convert,
    },
    'zh-hant': {
        'zh-hans': opencc.OpenCC('t2s.json').convert,
    },
}
CONVERTERS['zh'] = {
    'zh-hans': CONVERTERS['zh-hant']['zh-hans'],
    'zh-hant': CONVERTERS['zh-hans']['zh-hant'],
}


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

COUNTRIES = make_sorted_dict(COUNTRY_CODES, LOCALE_EN.territories)


def make_currencies_map():
    """Build a dict with country codes as keys and currency codes as values.

    This code is in a function so that its transient variables are garbage
    collected automatically, without needing an explicit `del` statement.
    """
    r = {}
    today = utcnow().date()
    for country, currencies in babel.core.get_global('territory_currencies').items():
        for currency, start_date, end_date, tender in currencies:
            if currency not in CURRENCIES:
                continue
            if start_date:
                start_date = date(*start_date)
            if end_date:
                end_date = date(*end_date)
            if (start_date is None or start_date <= today) and (end_date is None or end_date >= today):
                assert country not in r
                r[country] = currency
    for currency, (_, new_currency, _) in CURRENCY_REPLACEMENTS.items():
        if currency[:2] not in r:
            r[currency[:2]] = new_currency
    return r

CURRENCIES_MAP = make_currencies_map()


ACCEPTED_LANGUAGE_CODES = """
    af ak am ar as az be bg bm bn bo br bs ca cs cy da de dz ee el en eo es et
    eu fa ff fi fo fr ga gd gl gu gv ha he hi hr hu hy ia id ig ii is it ja ka
    ki kk kl km kn ko ks kw ky lg ln lo lt lu lv mg mk ml mn mr ms mt my nb nd
    ne nl nn om or os pa pl ps pt rm rn ro ru rw se sg si sk sl sn so sq sr sv
    sw ta te tg th ti to tr uk ur uz vi xh yo zh zh_Hans zh_Hant zu
""".split()

Locale.LANGUAGE_NAMES = {
    code.replace('_', '-').lower(): babel.localedata.load(code)['languages'][code]
    for code in ACCEPTED_LANGUAGE_CODES
}

del ACCEPTED_LANGUAGE_CODES

LOCALE_EN._data['languages'] = {
    intern(k.replace('_', '-').lower()): v for k, v in LOCALE_EN.languages.items()
}
ACCEPTED_LANGUAGES = make_sorted_dict(Locale.LANGUAGE_NAMES, LOCALE_EN.languages)

LOCALES = {}
LOCALE_EN = LOCALES['en'] = Locale('en')
LOCALE_EN.catalog = Catalog('en')
LOCALE_EN.catalog.plural_func = lambda n: n != 1
LOCALE_EN.missing_translations = 0
LOCALE_EN.fuzzy_translations = 0
LOCALE_EN.completion = 1
LOCALE_EN.countries = COUNTRIES
LOCALE_EN.accepted_languages = ACCEPTED_LANGUAGES
LOCALE_EN.supported_currencies = make_sorted_dict(
    CURRENCIES, LOCALE_EN.currencies, clean=Locale.title
)

# For languages that have multiple written forms, one of them must be chosen as the
# default, because the browser doesn't always specify which one the reader wants.
LOCALES_DEFAULT_MAP = {
    # Norwegian (no) has two main written forms: Bokmål (nb) and Nynorsk (nn).
    # We default to Bokmål because it's the most used.
    'no': 'nb',
    # Chinese (zh) has two main written forms: Traditional (zh-hant) and Simplified (zh-hans).
    # We default to Simplified because it's the most used.
    'zh': 'zh-hans',
    # For each territory, we default to the language in official use in that territory.
    'zh-cn': 'zh-hans-cn',
    'zh-hk': 'zh-hant-hk',
    'zh-mo': 'zh-hant-mo',
    'zh-sg': 'zh-hans-sg',
    'zh-tw': 'zh-hant-tw',
}

# https://www.postgresql.org/docs/13/textsearch-intro.html#TEXTSEARCH-INTRO-CONFIGURATIONS
SEARCH_CONFS = {
    'ar': 'arabic',
    'da': 'danish',
    'de': 'german',
    'el': 'greek',
    'en': 'english',
    'es': 'spanish',
    'fi': 'finnish',
    'fr': 'french',
    'ga': 'irish',
    'hu': 'hungarian',
    'id': 'indonesian',
    'it': 'italian',
    'lt': 'lithuanian',
    'nb': 'norwegian',
    'ne': 'nepali',
    'nl': 'dutch',
    'nn': 'norwegian',
    'pt': 'portuguese',
    'ro': 'romanian',
    'ru': 'russian',
    'sv': 'swedish',
    'ta': 'tamil',
    'tr': 'turkish',
}

_ = lambda a: a
HTTP_ERRORS = {
    403: _("Forbidden"),
    404: _("Not Found"),
    409: _("Conflict"),
    410: _("Gone"),
    429: _("Too Many Requests"),
    500: _("Internal Server Error"),
    502: _("Upstream Error"),
    503: _("Service Unavailable"),
    504: _("Gateway Timeout"),
}
del _


def getdoc(state, name):
    versions = state['website'].docs[name]
    for lang in state['request'].accept_langs:
        doc = versions.get(lang)
        if doc:
            return doc
    return versions['en']


def to_age(dt, **kw):
    kw.setdefault('add_direction', True)
    if isinstance(dt, datetime):
        delta = Age(dt - utcnow())
    elif isinstance(dt, timedelta):
        delta = Age(dt)
    else:
        delta = Age(dt - date.today())
        kw.setdefault('granularity', 'day')
    delta.format_args = kw
    return delta


def parse_accept_lang(accept_lang, limit=50):
    """Parse an HTTP `Accept-Language` header. Yields lowercase BCP47 tags.
    """
    langs = [
        lang.split(";", 1)[0].lower() for lang in accept_lang.split(",", limit) if lang
    ]
    if len(langs) > limit:
        langs.pop()
    langs_set = set(langs)
    for lang in langs:
        yield lang
        parts = lang.split('-')
        if len(parts) > 1 and parts[0] not in langs_set:
            # e.g. insert "fr" after "fr-fr" if it's not somewhere else in the list.
            # It would probably be better to insert the base lang after the
            # last matching sublang instead of after the first one, but that's
            # probably not worth the extra cost.
            yield parts[0]
            langs_set.add(parts[0])
        fallback_lang = LOCALES_DEFAULT_MAP.get(lang)
        if fallback_lang and fallback_lang not in langs_set:
            yield fallback_lang
            langs_set.add(fallback_lang)
    # Add English as the ultimate fallback.
    if 'en' not in langs_set:
        yield 'en'


def match_lang(languages, country=None):
    """
    Find the best locale based on the list of accepted languages and the country
    of origin of the request.
    """
    if country:
        country = country.lower()
    get_locale = LOCALES.get
    get_default = LOCALES_DEFAULT_MAP.get
    for lang in languages:
        if lang[-3:-2] != '-':
            territorial_lang = f"{lang}-{country}"
            loc = get_locale(territorial_lang) or get_locale(get_default(territorial_lang))
            if loc:
                return loc
        loc = get_locale(lang) or get_locale(get_default(lang))
        if loc:
            return loc
    return LOCALE_EN


def get_lang_options(request, locale, actively_used_langs, add_multi=False):
    """Get an ordered dict of languages (BCP47 tags as keys, display names as values).
    """
    langs = {}
    browser_langs = set(request.accept_langs)
    actively_used_langs = set(actively_used_langs)
    if actively_used_langs:
        langs.update(
            t for t in locale.accepted_languages.items()
            if t[0] in actively_used_langs
        )
        langs['-'] = '---'  # Separator
    langs.update(
        t for t in locale.accepted_languages.items()
        if t[0] in browser_langs
    )
    if len(langs) > (len(actively_used_langs) + 1):
        langs['--'] = '---'  # Separator
    if add_multi:
        langs['mul'] = locale.languages.get('mul', 'Multilingual')
    langs.update(locale.accepted_languages)
    return langs


def set_up_i18n(state, request=None, exception=None):
    if request is None:
        locale = LOCALE_EN
    else:
        langs = request.accept_langs = []
        subdomain = request.subdomain
        if subdomain:
            langs.append(subdomain)
            i = subdomain.find('-')
            if i > 0:
                langs.append(subdomain[:i])
        langs.extend(parse_accept_lang(
            request.headers.get(b"Accept-Language", b"").decode('ascii', 'replace')
        ))
        locale = match_lang(langs, request.source_country)
    add_helpers_to_context(state, locale)


def add_helpers_to_context(context, loc):
    context.update(
        escape=_return_,  # to be overridden by renderers
        locale=loc,
        Money=Money,
        _=lambda s, *a, **kw: loc._(context, s, *a, **kw),
        ngettext=lambda *a, **kw: loc.ngettext(context, *a, **kw),
    )


class DefaultString(str):
    __slots__ = ()

    def __bool__(self):
        return False


DEFAULT_CURRENCY = DefaultString('EUR')


def add_currency_to_state(request, user, locale):
    qs_currency = request.qs.get('currency')
    if qs_currency in CURRENCIES:
        return {'currency': qs_currency}
    cookie = request.headers.cookie.get('currency')
    if cookie and cookie.value in CURRENCIES:
        return {'currency': cookie.value}
    if user:
        return {'currency': user.main_currency}
    else:
        return {'currency': (
            CURRENCIES_MAP.get(locale.territory) or
            CURRENCIES_MAP.get(request.source_country) or
            DEFAULT_CURRENCY
        )}
