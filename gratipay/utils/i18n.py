# encoding: utf8
from __future__ import print_function, unicode_literals

from io import BytesIO
import re
from unicodedata import combining, normalize

from aspen.resources.pagination import parse_specline, split_and_escape
from aspen.utils import utcnow
from babel.core import LOCALE_ALIASES, Locale
from babel.dates import format_timedelta
from babel.messages.extract import extract_python
from babel.messages.pofile import Catalog
from babel.numbers import (
    format_currency, format_decimal, format_number, format_percent,
    get_decimal_symbol, parse_decimal
)
from collections import OrderedDict
import jinja2.ext


ALIASES = {k: v.lower() for k, v in LOCALE_ALIASES.items()}
ALIASES_R = {v: k for k, v in ALIASES.items()}

COUNTRIES = OrderedDict([
    ('AF', u'Afghanistan'),
    ('AX', u'\xc5land Islands'),
    ('AL', u'Albania'),
    ('DZ', u'Algeria'),
    ('AS', u'American Samoa'),
    ('AD', u'Andorra'),
    ('AO', u'Angola'),
    ('AI', u'Anguilla'),
    ('AQ', u'Antarctica'),
    ('AG', u'Antigua and Barbuda'),
    ('AR', u'Argentina'),
    ('AM', u'Armenia'),
    ('AW', u'Aruba'),
    ('AU', u'Australia'),
    ('AT', u'Austria'),
    ('AZ', u'Azerbaijan'),
    ('BS', u'Bahamas'),
    ('BH', u'Bahrain'),
    ('BD', u'Bangladesh'),
    ('BB', u'Barbados'),
    ('BY', u'Belarus'),
    ('BE', u'Belgium'),
    ('BZ', u'Belize'),
    ('BJ', u'Benin'),
    ('BM', u'Bermuda'),
    ('BT', u'Bhutan'),
    ('BO', u'Bolivia, Plurinational State of'),
    ('BQ', u'Bonaire, Sint Eustatius and Saba'),
    ('BA', u'Bosnia and Herzegovina'),
    ('BW', u'Botswana'),
    ('BV', u'Bouvet Island'),
    ('BR', u'Brazil'),
    ('IO', u'British Indian Ocean Territory'),
    ('BN', u'Brunei Darussalam'),
    ('BG', u'Bulgaria'),
    ('BF', u'Burkina Faso'),
    ('BI', u'Burundi'),
    ('KH', u'Cambodia'),
    ('CM', u'Cameroon'),
    ('CA', u'Canada'),
    ('CV', u'Cape Verde'),
    ('KY', u'Cayman Islands'),
    ('CF', u'Central African Republic'),
    ('TD', u'Chad'),
    ('CL', u'Chile'),
    ('CN', u'China'),
    ('CX', u'Christmas Island'),
    ('CC', u'Cocos (Keeling) Islands'),
    ('CO', u'Colombia'),
    ('KM', u'Comoros'),
    ('CG', u'Congo'),
    ('CD', u'Congo, The Democratic Republic of the'),
    ('CK', u'Cook Islands'),
    ('CR', u'Costa Rica'),
    ('CI', u"C\xf4te D'ivoire"),
    ('HR', u'Croatia'),
    ('CU', u'Cuba'),
    ('CW', u'Cura\xe7ao'),
    ('CY', u'Cyprus'),
    ('CZ', u'Czech Republic'),
    ('DK', u'Denmark'),
    ('DJ', u'Djibouti'),
    ('DM', u'Dominica'),
    ('DO', u'Dominican Republic'),
    ('EC', u'Ecuador'),
    ('EG', u'Egypt'),
    ('SV', u'El Salvador'),
    ('GQ', u'Equatorial Guinea'),
    ('ER', u'Eritrea'),
    ('EE', u'Estonia'),
    ('ET', u'Ethiopia'),
    ('FK', u'Falkland Islands (Malvinas)'),
    ('FO', u'Faroe Islands'),
    ('FJ', u'Fiji'),
    ('FI', u'Finland'),
    ('FR', u'France'),
    ('GF', u'French Guiana'),
    ('PF', u'French Polynesia'),
    ('TF', u'French Southern Territories'),
    ('GA', u'Gabon'),
    ('GM', u'Gambia'),
    ('GE', u'Georgia'),
    ('DE', u'Germany'),
    ('GH', u'Ghana'),
    ('GI', u'Gibraltar'),
    ('GR', u'Greece'),
    ('GL', u'Greenland'),
    ('GD', u'Grenada'),
    ('GP', u'Guadeloupe'),
    ('GU', u'Guam'),
    ('GT', u'Guatemala'),
    ('GG', u'Guernsey'),
    ('GN', u'Guinea'),
    ('GW', u'Guinea-bissau'),
    ('GY', u'Guyana'),
    ('HT', u'Haiti'),
    ('HM', u'Heard Island and McDonald Islands'),
    ('VA', u'Holy See (Vatican City State)'),
    ('HN', u'Honduras'),
    ('HK', u'Hong Kong'),
    ('HU', u'Hungary'),
    ('IS', u'Iceland'),
    ('IN', u'India'),
    ('ID', u'Indonesia'),
    ('IR', u'Iran, Islamic Republic of'),
    ('IQ', u'Iraq'),
    ('IE', u'Ireland'),
    ('IM', u'Isle of Man'),
    ('IL', u'Israel'),
    ('IT', u'Italy'),
    ('JM', u'Jamaica'),
    ('JP', u'Japan'),
    ('JE', u'Jersey'),
    ('JO', u'Jordan'),
    ('KZ', u'Kazakhstan'),
    ('KE', u'Kenya'),
    ('KI', u'Kiribati'),
    ('KP', u"Korea, Democratic People's Republic of"),
    ('KR', u'Korea, Republic of'),
    ('KW', u'Kuwait'),
    ('KG', u'Kyrgyzstan'),
    ('LA', u"Lao People's Democratic Republic"),
    ('LV', u'Latvia'),
    ('LB', u'Lebanon'),
    ('LS', u'Lesotho'),
    ('LR', u'Liberia'),
    ('LY', u'Libya'),
    ('LI', u'Liechtenstein'),
    ('LT', u'Lithuania'),
    ('LU', u'Luxembourg'),
    ('MO', u'Macao'),
    ('MK', u'Macedonia, The Former Yugoslav Republic of'),
    ('MG', u'Madagascar'),
    ('MW', u'Malawi'),
    ('MY', u'Malaysia'),
    ('MV', u'Maldives'),
    ('ML', u'Mali'),
    ('MT', u'Malta'),
    ('MH', u'Marshall Islands'),
    ('MQ', u'Martinique'),
    ('MR', u'Mauritania'),
    ('MU', u'Mauritius'),
    ('YT', u'Mayotte'),
    ('MX', u'Mexico'),
    ('FM', u'Micronesia, Federated States of'),
    ('MD', u'Moldova, Republic of'),
    ('MC', u'Monaco'),
    ('MN', u'Mongolia'),
    ('ME', u'Montenegro'),
    ('MS', u'Montserrat'),
    ('MA', u'Morocco'),
    ('MZ', u'Mozambique'),
    ('MM', u'Myanmar'),
    ('NA', u'Namibia'),
    ('NR', u'Nauru'),
    ('NP', u'Nepal'),
    ('NL', u'Netherlands'),
    ('NC', u'New Caledonia'),
    ('NZ', u'New Zealand'),
    ('NI', u'Nicaragua'),
    ('NE', u'Niger'),
    ('NG', u'Nigeria'),
    ('NU', u'Niue'),
    ('NF', u'Norfolk Island'),
    ('MP', u'Northern Mariana Islands'),
    ('NO', u'Norway'),
    ('OM', u'Oman'),
    ('PK', u'Pakistan'),
    ('PW', u'Palau'),
    ('PS', u'Palestinian Territory, Occupied'),
    ('PA', u'Panama'),
    ('PG', u'Papua New Guinea'),
    ('PY', u'Paraguay'),
    ('PE', u'Peru'),
    ('PH', u'Philippines'),
    ('PN', u'Pitcairn'),
    ('PL', u'Poland'),
    ('PT', u'Portugal'),
    ('PR', u'Puerto Rico'),
    ('QA', u'Qatar'),
    ('RE', u'R\xe9union'),
    ('RO', u'Romania'),
    ('RU', u'Russian Federation'),
    ('RW', u'Rwanda'),
    ('BL', u'Saint Barth\xe9lemy'),
    ('SH', u'Saint Helena, Ascension and Tristan Da Cunha'),
    ('KN', u'Saint Kitts and Nevis'),
    ('LC', u'Saint Lucia'),
    ('MF', u'Saint Martin (French Part)'),
    ('PM', u'Saint Pierre and Miquelon'),
    ('VC', u'Saint Vincent and the Grenadines'),
    ('WS', u'Samoa'),
    ('SM', u'San Marino'),
    ('ST', u'Sao Tome and Principe'),
    ('SA', u'Saudi Arabia'),
    ('SN', u'Senegal'),
    ('RS', u'Serbia'),
    ('SC', u'Seychelles'),
    ('SL', u'Sierra Leone'),
    ('SG', u'Singapore'),
    ('SX', u'Sint Maarten (Dutch Part)'),
    ('SK', u'Slovakia'),
    ('SI', u'Slovenia'),
    ('SB', u'Solomon Islands'),
    ('SO', u'Somalia'),
    ('ZA', u'South Africa'),
    ('GS', u'South Georgia and the South Sandwich Islands'),
    ('SS', u'South Sudan'),
    ('ES', u'Spain'),
    ('LK', u'Sri Lanka'),
    ('SD', u'Sudan'),
    ('SR', u'Suriname'),
    ('SJ', u'Svalbard and Jan Mayen'),
    ('SZ', u'Swaziland'),
    ('SE', u'Sweden'),
    ('CH', u'Switzerland'),
    ('SY', u'Syrian Arab Republic'),
    ('TW', u'Taiwan, Province of China'),
    ('TJ', u'Tajikistan'),
    ('TZ', u'Tanzania, United Republic of'),
    ('TH', u'Thailand'),
    ('TL', u'Timor-leste'),
    ('TG', u'Togo'),
    ('TK', u'Tokelau'),
    ('TO', u'Tonga'),
    ('TT', u'Trinidad and Tobago'),
    ('TN', u'Tunisia'),
    ('TR', u'Turkey'),
    ('TM', u'Turkmenistan'),
    ('TC', u'Turks and Caicos Islands'),
    ('TV', u'Tuvalu'),
    ('UG', u'Uganda'),
    ('UA', u'Ukraine'),
    ('AE', u'United Arab Emirates'),
    ('GB', u'United Kingdom'),
    ('US', u'United States'),
    ('UM', u'United States Minor Outlying Islands'),
    ('UY', u'Uruguay'),
    ('UZ', u'Uzbekistan'),
    ('VU', u'Vanuatu'),
    ('VE', u'Venezuela, Bolivarian Republic of'),
    ('VN', u'Viet Nam'),
    ('VG', u'Virgin Islands, British'),
    ('VI', u'Virgin Islands, U.S.'),
    ('WF', u'Wallis and Futuna'),
    ('EH', u'Western Sahara'),
    ('YE', u'Yemen'),
    ('ZM', u'Zambia'),
    ('ZW', u'Zimbabwe'),
])

LOCALES = {}
LOCALE_EN = LOCALES['en'] = Locale('en')
LOCALE_EN.catalog = Catalog('en')
LOCALE_EN.catalog.plural_func = lambda n: n != 1
LOCALE_EN.countries = COUNTRIES


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


def get_text(loc, s, *a, **kw):
    msg = loc.catalog.get(s)
    if msg:
        s = msg.string or s
    if a or kw:
        if isinstance(s, bytes):
            s = s.decode('ascii')
        return s.format(*a, **kw)
    return s


def n_get_text(tell_sentry, request, loc, s, p, n, *a, **kw):
    n = n or 0
    msg = loc.catalog.get((s, p))
    s2 = None
    if msg:
        try:
            s2 = msg.string[loc.catalog.plural_func(n)]
        except Exception as e:
            tell_sentry(e, request)
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


def strip_accents(s):
    return ''.join(c for c in normalize('NFKD', s) if not combining(c))


def parse_accept_lang(accept_lang):
    languages = (lang.split(";", 1)[0] for lang in accept_lang.split(","))
    return regularize_locales(languages)


def match_lang(languages):
    for lang in languages:
        loc = LOCALES.get(lang)
        if loc:
            return loc
    return LOCALE_EN


def format_currency_with_options(number, currency, locale='en', trailing_zeroes=True):
    s = format_currency(number, currency, locale=locale)
    if not trailing_zeroes:
        s = s.replace(get_decimal_symbol(locale)+'00', '')
    return s


def set_up_i18n(website, request):
    accept_lang = request.headers.get("Accept-Language", "")
    langs = request.accept_langs = list(parse_accept_lang(accept_lang))
    loc = match_lang(langs)
    add_helpers_to_context(website.tell_sentry, request.context, loc, request)


def add_helpers_to_context(tell_sentry, context, loc, request=None):
    context['locale'] = loc
    context['decimal_symbol'] = get_decimal_symbol(locale=loc)
    context['_'] = lambda s, *a, **kw: get_text(loc, s, *a, **kw)
    context['ngettext'] = lambda *a, **kw: n_get_text(tell_sentry, request, loc, *a, **kw)
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
