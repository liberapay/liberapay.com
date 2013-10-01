import time

import gittip
from aspen import log_dammit, Response
from aspen.utils import typecheck
from tornado.escape import linkify


COUNTRIES = (
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
)
COUNTRIES_MAP = dict(COUNTRIES)


def wrap(u):
    """Given a unicode, return a unicode.
    """
    typecheck(u, unicode)
    u = linkify(u)  # Do this first, because it calls xthml_escape.
    u = u.replace(u'\r\n', u'<br />\r\n').replace(u'\n', u'<br />\n')
    return u if u else '...'


def dict_to_querystring(mapping):
    if not mapping:
        return u''

    arguments = []
    for key, values in mapping.iteritems():
        for val in values:
            arguments.append(u'='.join([key, val]))

    return u'?' + u'&'.join(arguments)

def canonicalize(path, base, canonical, given, arguments=None):
    if given != canonical:
        assert canonical.lower() == given.lower()  # sanity check
        remainder = path[len(base + given):]

        if arguments is not None:
            arguments = dict_to_querystring(arguments)

        newpath = base + canonical + remainder + arguments or ''
        raise Response(302, headers={"Location": newpath})


def plural(i, singular="", plural="s"):
    return singular if i == 1 else plural


def get_participant(request, restrict=True):
    """Given a Request, raise Response or return Participant.

    If user is not None then we'll restrict access to owners and admins.

    """
    user = request.context['user']
    slug = request.line.uri.path['username']
    qs = request.line.uri.querystring

    if restrict:
        if user.ANON:
            request.redirect(u'/%s/' % slug)

    participant = gittip.db.one( "SELECT participants.*::participants "
                                         "FROM participants "
                                         "WHERE username_lower=%s"
                                       , (slug.lower(),)
                                        )

    if participant is None:
        raise Response(404)

    canonicalize(request.line.uri.path.raw, '/', participant.username, slug, qs)

    if participant.claimed_time is None:

        # This is a stub participant record for someone on another platform who
        # hasn't actually registered with Gittip yet. Let's bounce the viewer
        # over to the appropriate platform page.

        to = participant.resolve_unclaimed()
        if to is None:
            raise Response(404)
        request.redirect(to)

    if restrict:
        if participant != user.participant:
            if not user.ADMIN:
                raise Response(403)

    return participant


def update_homepage_queries_once(db):
    with db.get_cursor() as cursor:
        log_dammit("updating homepage queries")
        start = time.time()
        cursor.execute("""

        DROP TABLE IF EXISTS _homepage_new_participants;
        CREATE TABLE _homepage_new_participants AS
              SELECT username, claimed_time FROM (
                  SELECT DISTINCT ON (p.username)
                         p.username
                       , claimed_time
                    FROM participants p
                    JOIN elsewhere e
                      ON p.username = participant
                   WHERE claimed_time IS NOT null
                     AND is_suspicious IS NOT true
                     ) AS foo
            ORDER BY claimed_time DESC;

        DROP TABLE IF EXISTS _homepage_top_givers;
        CREATE TABLE _homepage_top_givers AS
            SELECT tipper AS username, anonymous, sum(amount) AS amount
              FROM (    SELECT DISTINCT ON (tipper, tippee)
                               amount
                             , tipper
                          FROM tips
                          JOIN participants p ON p.username = tipper
                          JOIN participants p2 ON p2.username = tippee
                          JOIN elsewhere ON elsewhere.participant = tippee
                         WHERE p.last_bill_result = ''
                           AND p.is_suspicious IS NOT true
                           AND p2.claimed_time IS NOT NULL
                           AND elsewhere.is_locked = false
                      ORDER BY tipper, tippee, mtime DESC
                      ) AS foo
              JOIN participants p ON p.username = tipper
             WHERE is_suspicious IS NOT true
          GROUP BY tipper, anonymous
          ORDER BY amount DESC;

        DROP TABLE IF EXISTS _homepage_top_receivers;
        CREATE TABLE _homepage_top_receivers AS
            SELECT tippee AS username, claimed_time, sum(amount) AS amount
              FROM (    SELECT DISTINCT ON (tipper, tippee)
                               amount
                             , tippee
                          FROM tips
                          JOIN participants p ON p.username = tipper
                          JOIN elsewhere ON elsewhere.participant = tippee
                         WHERE last_bill_result = ''
                           AND elsewhere.is_locked = false
                           AND is_suspicious IS NOT true
                           AND claimed_time IS NOT null
                      ORDER BY tipper, tippee, mtime DESC
                      ) AS foo
              JOIN participants p ON p.username = tippee
             WHERE is_suspicious IS NOT true
          GROUP BY tippee, claimed_time
          ORDER BY amount DESC;

        DROP TABLE IF EXISTS homepage_new_participants;
        ALTER TABLE _homepage_new_participants
          RENAME TO homepage_new_participants;

        DROP TABLE IF EXISTS homepage_top_givers;
        ALTER TABLE _homepage_top_givers
          RENAME TO homepage_top_givers;

        DROP TABLE IF EXISTS homepage_top_receivers;
        ALTER TABLE _homepage_top_receivers
          RENAME TO homepage_top_receivers;

        """)
        end = time.time()
        elapsed = end - start
        log_dammit("updated homepage queries in %.2f seconds" % elapsed)
