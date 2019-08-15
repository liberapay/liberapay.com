from collections import namedtuple, OrderedDict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from unicodedata import combining, normalize

import babel.core
from babel.dates import format_date, format_datetime, format_time, format_timedelta
from babel.messages.pofile import Catalog
from babel.numbers import parse_pattern
from markupsafe import Markup
from pando.utils import utcnow

from ..constants import CURRENCIES, D_MAX
from ..exceptions import AmbiguousNumber, InvalidNumber
from ..website import website
from .currencies import Money, MoneyBasket


MONEY_AMOUNT_FORMAT = parse_pattern('#,##0.00')
ONLY_ZERO = {'0'}


def no_escape(s):
    return s


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


class List(list):
    __slots__ = ('pattern',)

    def __init__(self, iterable, pattern='standard'):
        list.__init__(self, iterable)
        self.pattern = pattern


class Percent(Decimal):
    __slots__ = ()


class Age(timedelta):

    def __new__(cls, *a, **kw):
        if len(a) == 1 and not kw and isinstance(a[0], timedelta):
            return timedelta.__new__(cls, a[0].days, a[0].seconds, a[0].microseconds)
        return timedelta.__new__(cls, *a, **kw)


class Locale(babel.core.Locale):

    List = List

    def __init__(self, *a, **kw):
        super(Locale, self).__init__(*a, **kw)
        self.currency_formats['amount_only'] = MONEY_AMOUNT_FORMAT
        delta_p = self.currency_formats['standard'].pattern
        minus_sign = self.number_symbols.get('minusSign', '-')
        plus_sign = self.number_symbols.get('plusSign', '+')
        if ';' in delta_p:
            pos, neg = delta_p.split(';')
            assert len(neg) > len(pos)
            assert minus_sign in neg
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
        if not s2:
            s2 = s
            if self is not LOCALE_EN:
                self = LOCALE_EN
                state['partial_translation'] = True
        if a or kw:
            try:
                return self.format(escape(s2), *a, **kw)
            except Exception as e:
                website.tell_sentry(e, state)
                return LOCALE_EN.format(escape(s), *a, **kw)
        return escape(s2)

    def ngettext(self, state, s, p, n, *a, **kw):
        escape = state['escape']
        n, wrapper = (n.value, n.wrapper) if isinstance(n, Wrap) else (n, None)
        n = n or 0
        msg = self.catalog._messages.get(s if s else p)
        s2 = None
        if msg:
            try:
                s2 = msg.string[self.catalog.plural_func(n)]
            except Exception as e:
                website.tell_sentry(e, state)
        if not s2:
            s2 = s if n == 1 else p
            if self is not LOCALE_EN:
                self = LOCALE_EN
                state['partial_translation'] = True
        kw['n'] = self.format_decimal(n) or n
        if wrapper:
            kw['n'] = wrapper % kw['n']
        try:
            return self.format(escape(s2), *a, **kw)
        except Exception as e:
            website.tell_sentry(e, state)
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
                elif isinstance(o, (Decimal, int)):
                    if isinstance(o, Percent):
                        o = self.format_percent(o)
                    else:
                        o = self.format_decimal(o)
                elif isinstance(o, Money):
                    o = self.format_money(o)
                elif isinstance(o, MoneyBasket):
                    o = self.format_money_basket(o)
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
                    escape = getattr(s.__class__, 'escape', no_escape)
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
            decimal_quantization=True
        )
        if trailing_zeroes is False:
            i = s.find(self.number_symbols['decimal'])
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
        return self.decimal_formats[None].apply(number, self, **kw)

    def format_list(self, l, pattern='standard', escape=no_escape):
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
            pattern.apply(money.amount, self, currency=money.currency)
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
            decimal_quantization=True
        )

    def format_percent(self, number, **kw):
        return self.percent_formats[None].apply(number, self, **kw)

    def format_time(self, t, format='medium'):
        return format_time(t, format=format, locale=self)

    def format_timedelta(self, o, **kw):
        if type(o) is Age:
            kw.update(o.format_args)
        return format_timedelta(o, locale=self, **kw)

    def parse_money_amount(self, string, currency, maximum=D_MAX):
        group_symbol = self.number_symbols['group']
        decimal_symbol = self.number_symbols['decimal']
        try:
            decimal = Decimal(
                string.replace(group_symbol, '').replace(decimal_symbol, '.')
            )
        except (InvalidOperation, ValueError):
            raise InvalidNumber(string)
        if group_symbol in string:
            proper = self.format_decimal(decimal, decimal_quantization=False)
            if string != proper and string.rstrip('0') != (proper + decimal_symbol):
                # Irregular number format (e.g. `10.00` in German)
                try:
                    decimal_alt = Decimal(
                        string.replace(decimal_symbol, '').replace(group_symbol, '.')
                    )
                except (InvalidOperation, ValueError):
                    raise AmbiguousNumber(string, [proper])
                else:
                    proper_alt = self.format_decimal(decimal_alt, decimal_quantization=False)
                    raise AmbiguousNumber(string, [proper, proper_alt])
        if maximum is not None and decimal > maximum:
            raise InvalidNumber(string)
        money = Money(decimal, currency).round_down()
        if money.amount != decimal:
            # The input amount exceeds maximum precision (e.g. $0.001).
            raise InvalidNumber(string)
        return money

    @staticmethod
    def title(s):
        return s[0].upper() + s[1:] if s and s[0].islower() else s

    @property
    def subdomain(self):
        return 'zh' if self.language == 'zh_Hant' else self.language


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

CURRENCIES_MAP = {}
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
            assert country not in CURRENCIES_MAP
            CURRENCIES_MAP[country] = currency
del today

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


def set_up_i18n(state, request=None, exception=None):
    if request is None:
        add_helpers_to_context(state, LOCALE_EN)
        return
    accept_lang = request.headers.get(b"Accept-Language", b"").decode('ascii', 'replace')
    langs = request.accept_langs = list(parse_accept_lang(accept_lang))
    loc = match_lang(langs)
    add_helpers_to_context(state, loc)


def _return_(a):
    return a


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


def add_currency_to_state(request, user):
    qs_currency = request.qs.get('currency')
    if qs_currency in CURRENCIES:
        return {'currency': qs_currency}
    cookie = request.headers.cookie.get('currency')
    if cookie and cookie.value in CURRENCIES:
        return {'currency': cookie.value}
    if user:
        return {'currency': user.main_currency}
    else:
        return {'currency': CURRENCIES_MAP.get(request.country) or DEFAULT_CURRENCY}
