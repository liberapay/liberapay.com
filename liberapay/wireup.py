# coding: utf8
from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal
from ipaddress import ip_network
import json
import logging
import os
import re
import socket
import signal
from subprocess import call
from time import time
import traceback

_str = str
from six import text_type as str
from six.moves.urllib.parse import quote as urlquote
from six.moves.urllib.request import urlretrieve

from algorithm import Algorithm
import pando
from babel.messages.pofile import read_po
from babel.numbers import parse_pattern
import boto3
from environment import Environment, is_yesish
from mailshake import DummyMailer, SMTPMailer
from mangopay.utils import Money
import psycopg2
from psycopg2.extensions import adapt, AsIs, new_type, register_adapter, register_type
import raven
import sass

from liberapay import elsewhere
import liberapay.billing.payday
import liberapay.billing.watcher
from liberapay.constants import CustomUndefined
from liberapay.exceptions import NeedDatabase
from liberapay.models.account_elsewhere import _AccountElsewhere, AccountElsewhere
from liberapay.models.community import _Community, Community
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.models.repository import Repository
from liberapay.models import DB
from liberapay.utils import find_files, markdown, mkdir_p, resolve
from liberapay.utils.currencies import MoneyBasket, get_currency_exchange_rates
from liberapay.utils.emails import compile_email_spt
from liberapay.utils.http_caching import asset_etag
from liberapay.utils.i18n import (
    ALIASES, ALIASES_R, COUNTRIES, LANGUAGES_2, LOCALES, Locale,
    get_function_from_rule, make_sorted_dict
)
from liberapay.utils.query_cache import QueryCache
from liberapay.version import get_version


def canonical(env):
    canonical_scheme = env.canonical_scheme
    canonical_host = env.canonical_host
    cookie_domain = None
    if canonical_host:
        canonical_url = '%s://%s' % (canonical_scheme, canonical_host)
        if ':' not in canonical_host:
            cookie_domain = ('.' + canonical_host).encode('ascii')
    else:
        canonical_url = ''
    asset_url = canonical_url+'/assets/'
    return locals()


class CSP(bytes):

    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/default-src
    based_on_default_src = set(b'''
        child-src connect-src font-src frame-src img-src manifest-src
        media-src object-src script-src style-src worker-src
    '''.split())

    def __new__(cls, x):
        if isinstance(x, dict):
            self = bytes.__new__(cls, b';'.join(b' '.join(t).rstrip() for t in x.items()) + b';')
            self.directives = dict(x)
        else:
            self = bytes.__new__(cls, x)
            self.directives = dict(
                (d.split(b' ', 1) + [b''])[:2] for d in self.split(b';') if d
            )
        return self

    def allow(self, directive, value):
        d = dict(self.directives)
        old_value = d.get(directive)
        if old_value is None and directive in self.based_on_default_src:
            old_value = d.get(b'default-src')
        d[directive] = b'%s %s' % (old_value, value) if old_value else value
        return CSP(d)


def csp(canonical_host, canonical_scheme, env):
    csp = (
        b"default-src 'self' %(main_domain)s;"
        b"connect-src 'self' *.liberapay.org *.mangopay.com *.payline.com;"
        b"form-action 'self';"
        b"img-src * blob: data:;"
        b"object-src 'none';"
    ) % {b'main_domain': canonical_host.encode('ascii')}
    csp += env.csp_extra.encode()
    if canonical_scheme == 'https':
        csp += b"upgrade-insecure-requests;"
    return {'csp': CSP(csp)}


class NoDB(object):

    def __getattr__(self, attr):
        raise NeedDatabase()

    __bool__ = lambda self: False
    __nonzero__ = __bool__

    def register_model(self, model):
        model.db = self


def database(env, tell_sentry):
    dburl = env.database_url
    maxconn = env.database_maxconn
    try:
        db = DB(dburl, maxconn=maxconn)
    except psycopg2.OperationalError as e:
        tell_sentry(e, {})
        pg_dir = os.environ.get('OPENSHIFT_PG_DATA_DIR')
        if pg_dir:
            # We know where the postgres data is, try to start the server ourselves
            r = call(['pg_ctl', '-D', pg_dir, 'start', '-w', '-t', '15'])
            if r == 0:
                return database(env, tell_sentry)
        db = NoDB()

    models = (
        _AccountElsewhere, AccountElsewhere, _Community, Community,
        ExchangeRoute, Participant, Repository,
    )
    for model in models:
        db.register_model(model)
    liberapay.billing.payday.Payday.db = db

    def adapt_money(m):
        return AsIs('(%s,%s)::currency_amount' % (adapt(m.amount), adapt(m.currency)))
    register_adapter(Money, adapt_money)

    def cast_currency_amount(v, cursor):
        return None if v in (None, '(,)') else Money(*v[1:-1].split(','))
    try:
        oid = db.one("SELECT 'currency_amount'::regtype::oid")
        register_type(new_type((oid,), _str('currency_amount'), cast_currency_amount))
    except psycopg2.ProgrammingError:
        pass

    def adapt_money_basket(b):
        return AsIs('(%s,%s)::currency_basket' % (b.amounts['EUR'], b.amounts['USD']))
    register_adapter(MoneyBasket, adapt_money_basket)

    def cast_currency_basket(v, cursor):
        if v is None:
            return None
        eur, usd = v[1:-1].split(',')
        return MoneyBasket(EUR=Decimal(eur), USD=Decimal(usd))
    try:
        oid = db.one("SELECT 'currency_basket'::regtype::oid")
        register_type(new_type((oid,), _str('currency_basket'), cast_currency_basket))
    except psycopg2.ProgrammingError:
        pass

    use_qc = not env.override_query_cache
    qc1 = QueryCache(db, threshold=(1 if use_qc else 0))
    qc5 = QueryCache(db, threshold=(5 if use_qc else 0))

    return {'db': db, 'db_qc1': qc1, 'db_qc5': qc5}


class AppConf(object):

    fields = dict(
        app_name=str,
        bitbucket_callback=str,
        bitbucket_id=str,
        bitbucket_secret=str,
        bot_github_token=str,
        bot_github_username=str,
        bountysource_api_url=str,
        bountysource_auth_url=str,
        bountysource_callback=str,
        bountysource_id=None.__class__,
        bountysource_secret=str,
        check_db_every=int,
        clean_up_counters_every=int,
        dequeue_emails_every=int,
        facebook_callback=str,
        facebook_id=str,
        facebook_secret=str,
        github_callback=str,
        github_id=str,
        github_secret=str,
        gitlab_callback=str,
        gitlab_id=str,
        gitlab_secret=str,
        google_callback=str,
        google_id=str,
        google_secret=str,
        linuxfr_callback=str,
        linuxfr_id=str,
        linuxfr_secret=str,
        log_emails=bool,
        mangopay_base_url=str,
        mangopay_client_id=str,
        mangopay_client_password=str,
        openstreetmap_api_url=str,
        openstreetmap_auth_url=str,
        openstreetmap_callback=str,
        openstreetmap_id=str,
        openstreetmap_secret=str,
        password_rounds=int,
        payday_label=str,
        payday_repo=str,
        refetch_repos_every=int,
        s3_endpoint=str,
        s3_public_access_key=str,
        s3_secret_key=str,
        s3_region=str,
        s3_payday_logs_bucket=str,
        send_newsletters_every=int,
        show_sandbox_warning=bool,
        socket_timeout=float,
        smtp_host=str,
        smtp_port=int,
        smtp_username=str,
        smtp_password=str,
        smtp_use_tls=bool,
        trusted_proxies=list,
        twitch_id=str,
        twitch_secret=str,
        twitter_callback=str,
        twitter_id=str,
        twitter_secret=str,
    )

    def __init__(self, d):
        d = d if isinstance(d, dict) else dict(d)

        unexpected = set(d) - set(self.fields)
        if unexpected:
            print("Found %i unexpected variables in the app_conf table:  %s" %
                  (len(unexpected), ' '.join(unexpected)))

        missing, mistyped = [], []
        for k, t in self.fields.items():
            if k in d:
                v = d[k]
                if isinstance(v, t):
                    self.__dict__[k] = v
                else:
                    mistyped.append((k, v, t))
            else:
                missing.append(k)
        if missing:
            print('Missing configuration variables: ', ' '.join(missing))
        for k, v, t in mistyped:
            print('Invalid configuration variable, %s: %s is of type %s, not %s' %
                  (k, json.dumps(v), type(v), t))

        self.missing = missing
        self.mistyped = mistyped
        self.unexpected = unexpected


def app_conf(db):
    if not db:
        return {'app_conf': None}
    app_conf = AppConf(db.all("SELECT key, value FROM app_conf"))
    if app_conf:
        socket.setdefaulttimeout(app_conf.socket_timeout)
    return {'app_conf': app_conf}


def trusted_proxies(app_conf, env, tell_sentry):
    if not app_conf:
        return {'trusted_proxies': []}
    def parse_network(net):
        if net == 'private':
            return [net]
        elif net.startswith('https://'):
            d = env.log_dir + '/trusted_proxies/'
            mkdir_p(d)
            filename = d + urlquote(net, '')
            skip_download = (
                os.path.exists(filename) and
                os.stat(filename).st_size > 0 and
                os.stat(filename).st_mtime > time() - 60*60*24*7
            )
            if not skip_download:
                urlretrieve(net, filename)
            with open(filename, 'rb') as f:
                return [ip_network(x) for x in f.read().decode('ascii').strip().split()]
        else:
            return [ip_network(net)]
    try:
        return {'trusted_proxies': [
            sum((parse_network(net) for net in networks), [])
            for networks in (app_conf.trusted_proxies or ())
        ]}
    except Exception as e:
        tell_sentry(e, {})
        return {'trusted_proxies': []}


def mail(app_conf, project_root='.'):
    if not app_conf:
        return
    smtp_conf = {
        k[5:]: v for k, v in app_conf.__dict__.items() if k.startswith('smtp_')
    }
    if smtp_conf:
        smtp_conf.setdefault('timeout', app_conf.socket_timeout)
    mailer = SMTPMailer(**smtp_conf) if smtp_conf else DummyMailer()
    emails = {}
    emails_dir = project_root+'/emails/'
    i = len(emails_dir)
    for spt in find_files(emails_dir, '*.spt'):
        base_name = spt[i:-4]
        emails[base_name] = compile_email_spt(spt)

    def log_email(message):
        message = dict(message)
        html, text = message.pop('html'), message.pop('text')
        print('\n', ' ', '='*26, 'BEGIN EMAIL', '='*26)
        print(json.dumps(message))
        print('[---] text/html')
        print(html)
        print('[---] text/plain')
        print(text)
        print('  ', '='*27, 'END EMAIL', '='*27)

    log_email = log_email if app_conf.log_emails else lambda *a, **kw: None

    return {'emails': emails, 'log_email': log_email, 'mailer': mailer}


def billing(app_conf):
    if not app_conf:
        return
    import mangopay
    sandbox = 'sandbox' in app_conf.mangopay_base_url
    mangopay.sandbox = sandbox
    handler = mangopay.APIRequest(
        client_id=app_conf.mangopay_client_id,
        passphrase=app_conf.mangopay_client_password,
        sandbox=sandbox,
        timeout=app_conf.socket_timeout,
    )
    mangopay.get_default_handler = mangopay.base.get_default_handler = \
        mangopay.query.get_default_handler = lambda: handler

    # https://github.com/Mangopay/mangopay2-python-sdk/issues/95
    if not sandbox:
        mangopay.api.logger.setLevel(logging.CRITICAL)

    # https://github.com/Mangopay/mangopay2-python-sdk/issues/118
    mangopay.resources.LegalUser.person_type = 'LEGAL'

    # https://github.com/Mangopay/mangopay2-python-sdk/issues/144
    mangopay.signals.request_finished.connect(liberapay.billing.watcher.on_response)


def username_restrictions(www_root):
    return {'restricted_usernames': os.listdir(www_root)}


def make_sentry_teller(env):
    if env.sentry_dsn:
        try:
            release = get_version()
            if '-' in release:
                release = None
        except:
            release = None
        sentry = raven.Client(
            env.sentry_dsn,
            environment=env.instance_type,
            release=release,
        )
    else:
        sentry = None
        print("Won't log to Sentry (SENTRY_DSN is empty).")

    def tell_sentry(exception, state, allow_reraise=True):

        if isinstance(exception, pando.Response) and exception.code < 500:
            # Only log server errors
            return

        if isinstance(exception, NeedDatabase):
            # Don't flood Sentry when DB is down
            return

        if isinstance(exception, psycopg2.Error):
            from liberapay.website import website
            if getattr(website, 'db', None):
                try:
                    website.db.one('SELECT 1 AS x')
                except psycopg2.Error:
                    # If it can't answer this simple query, it's down.
                    website.db = NoDB()
                    # Show the proper 503 error page
                    state['exception'] = NeedDatabase()
                    # Tell gunicorn to gracefully restart this worker
                    os.kill(os.getpid(), signal.SIGTERM)

                if 'read-only' in str(exception):
                    # DB is in read only mode
                    state['db_is_readonly'] = True
                    # Show the proper 503 error page
                    state['exception'] = NeedDatabase()
                    # Don't reraise this in tests
                    allow_reraise = False

        if isinstance(exception, ValueError):
            if 'cannot contain NUL (0x00) characters' in str(exception):
                # https://github.com/liberapay/liberapay.com/issues/675
                response = state.get('response') or pando.Response()
                response.code = 400
                response.body = str(exception)
                return {'exception': None}

        if not sentry:
            # No Sentry, log to stderr instead
            traceback.print_exc()
            # Reraise if allowed
            if env.sentry_reraise and allow_reraise:
                raise
            return {'sentry_ident': None}

        # Prepare context data
        sentry_data = {}
        if state:
            try:
                sentry_data['tags'] = {
                    'lang': getattr(state.get('locale'), 'language', None),
                }
                request = state.get('request')
                user_data = sentry_data['user'] = {}
                if request is not None:
                    user_data['ip_address'] = str(request.source)
                    sentry_data['request'] = {
                        'method': request.method,
                        'url': request.line.uri,
                        'headers': {
                            k: b', '.join(v) for k, v in request.headers.items()
                            if k != b'Cookie'
                        },
                    }
                user = state.get('user')
                if isinstance(user, Participant):
                    user_data['id'] = getattr(user, 'id', None)
                    user_data['username'] = getattr(user, 'username', None)
            except Exception as e:
                tell_sentry(e, {})

        # Tell Sentry
        result = sentry.captureException(data=sentry_data)

        # Put the Sentry id in the state for logging, etc
        return {'sentry_ident': sentry.get_ident(result)}

    CustomUndefined._tell_sentry = staticmethod(tell_sentry)

    return {'tell_sentry': tell_sentry}


class PlatformRegistry(object):
    """Registry of platforms we support.
    """
    def __init__(self, platforms):
        self.list = platforms
        self.dict = dict((p.name, p) for p in platforms)
        self.__dict__.update(self.dict)
        self._hasattr_cache = {}

    def __contains__(self, platform):
        return platform.name in self.dict

    def __iter__(self):
        return iter(self.list)

    def __len__(self):
        return len(self.list)

    def _cache_hasattr(self, attr):
        r = PlatformRegistry([p for p in self if getattr(p, attr, None)])
        self._hasattr_cache[attr] = r
        return r

    def get(self, k, default=None):
        return self.dict.get(k, default)

    def hasattr(self, attr):
        r = self._hasattr_cache.get(attr)
        return r or self._cache_hasattr(attr)


def accounts_elsewhere(app_conf, asset, canonical_url, db):
    if not app_conf:
        return
    platforms = []
    for cls in elsewhere.CLASSES:
        conf = {
            k[len(cls.name)+1:]: v
            for k, v in app_conf.__dict__.items() if k.startswith(cls.name+'_')
        }
        conf.setdefault('api_timeout', app_conf.socket_timeout)
        conf.setdefault('app_name', app_conf.app_name)
        conf.setdefault('app_url', canonical_url)
        if hasattr(cls, 'register_app'):
            callback_url = canonical_url + '/on/' + cls.name + ':{domain}/associate'
            platforms.append(cls(None, None, callback_url, **conf))
        elif hasattr(cls, 'based_on'):
            based_on = cls.based_on
            callback_url = canonical_url + '/on/' + cls.name + '/associate'
            platforms.append(cls(
                getattr(app_conf, based_on + '_id'),
                getattr(app_conf, based_on + '_secret'),
                callback_url,
                **conf
            ))
        else:
            platforms.append(cls(
                conf.pop('id'),
                conf.pop('secret'),
                conf.pop('callback', canonical_url + '/on/' + cls.name + '/associate'),
                **conf
            ))

    platforms = [p for p in platforms if p.api_secret or hasattr(p, 'register_app')]
    order = db.all("""
        SELECT platform
          FROM (
            SELECT e.platform, count(*) as c
              FROM elsewhere e
              JOIN participants p ON p.id = e.participant
             WHERE p.status = 'active'
               AND p.hide_from_lists = 0
          GROUP BY e.platform
               ) a
      ORDER BY c DESC, platform ASC
    """)
    n = len(order)
    order = dict(zip(order, range(n)))
    platforms = sorted(platforms, key=lambda p: (order.get(p.name, n), p.name))
    platforms = PlatformRegistry(platforms)

    friends_platforms = [p for p in platforms if getattr(p, 'api_friends_path', None)]
    friends_platforms = PlatformRegistry(friends_platforms)

    for platform in platforms:
        platform.icon = asset('platforms/%s.16.png' % platform.name)
        platform.logo = asset('platforms/%s.png' % platform.name)

    return {'platforms': platforms, 'friends_platforms': friends_platforms}


def replace_unused_singulars(c):
    for m in list(c):
        msg = m.id
        if not isinstance(msg, tuple):
            continue
        if msg[0].startswith('<unused singular (hash='):
            del c[msg[0]]
            c[msg[1]] = m


def load_i18n(canonical_host, canonical_scheme, project_root, tell_sentry):
    # Load the locales
    localeDir = os.path.join(project_root, 'i18n', 'core')
    locales = LOCALES
    for file in os.listdir(localeDir):
        try:
            parts = file.split(".")
            if not (len(parts) == 2 and parts[1] == "po"):
                continue
            lang = parts[0]
            with open(os.path.join(localeDir, file)) as f:
                l = locales[lang.lower()] = Locale(lang)
                c = l.catalog = read_po(f)
                c.plural_func = get_function_from_rule(c.plural_expr)
                replace_unused_singulars(c)
                try:
                    l.countries = make_sorted_dict(COUNTRIES, l.territories)
                except KeyError:
                    l.countries = COUNTRIES
                try:
                    l.languages_2 = make_sorted_dict(LANGUAGES_2, l.languages)
                except KeyError:
                    l.languages_2 = LANGUAGES_2
        except Exception as e:
            tell_sentry(e, {})

    # Prepare a unique and sorted list for use in the language switcher
    percent = lambda l, total: sum((percent(s, len(s)) if isinstance(s, tuple) else 1) for s in l if s) / total
    for l in list(locales.values()):
        if l.language == 'en':
            l.completion = 1
            continue
        l.completion = percent([m.string for m in l.catalog if m.id and not m.fuzzy], len(l.catalog))
        if l.completion == 0:
            del locales[l.language]
    loc_url = canonical_scheme+'://%s.'+canonical_host
    domain, port = (canonical_host.split(':') + [None])[:2]
    port = int(port) if port else socket.getservbyname(canonical_scheme, 'tcp')
    subdomains = {k: loc_url % k for k in locales if resolve(k + '.' + domain, port)}
    lang_list = sorted(
        (
            (l.completion, l.language, l.language_name.title(), loc_url % l.language)
            for l in set(locales.values()) if l.completion > 0.5
        ),
        key=lambda t: (-t[0], t[1]),
    )

    # Add year-less date format
    year_re = re.compile(r'(^y+[^a-zA-Z]+|[^a-zA-Z]+y+$)')
    for l in locales.values():
        short_format = l.date_formats['short'].pattern
        assert short_format[0] == 'y' or short_format[-1] == 'y', (l.language, short_format)
        l.date_formats['short_yearless'] = year_re.sub('', short_format)

    # Add aliases
    for k, v in list(locales.items()):
        locales.setdefault(ALIASES.get(k, k), v)
        locales.setdefault(ALIASES_R.get(k, k), v)
    for k, v in list(locales.items()):
        locales.setdefault(k.split('_', 1)[0], v)

    # Patch the locales to look less formal
    locales['fr'].currency_formats['standard'] = parse_pattern('#,##0.00\u202f\xa4')
    locales['fr'].currency_symbols['USD'] = '$'
    locales['fr'].currencies['USD'] = 'dollar états-unien'

    # Load the markdown files
    docs = {}
    heading_re = re.compile(r'^(#+ )', re.M)
    for path in find_files(os.path.join(project_root, 'i18n'), '*.md'):
        d, b = os.path.split(path)
        doc = os.path.basename(d)
        lang = b[:-3]
        with open(path, 'rb') as f:
            md = f.read().decode('utf8')
            if md.startswith('# '):
                md = '\n'.join(md.split('\n')[1:]).strip()
                md = heading_re.sub(r'##\1', md)
            docs.setdefault(doc, {}).__setitem__(lang, markdown.render(md))

    return {'docs': docs, 'lang_list': lang_list, 'locales': locales, 'subdomains': subdomains}


def asset_url_generator(env, asset_url, tell_sentry, www_root):
    if env.cache_static:
        def asset(path):
            fspath = www_root+'/assets/'+path
            etag = ''
            try:
                etag = asset_etag(fspath)
            except Exception as e:
                tell_sentry(e, {})
            return asset_url+path+(etag and '?etag='+etag)
    else:
        asset = lambda path: asset_url+path
    return {'asset': asset}


def env():
    env = Environment(
        ASPEN_PROJECT_ROOT=str,
        AWS_ACCESS_KEY_ID=str,
        AWS_SECRET_ACCESS_KEY=str,
        DATABASE_URL=str,
        DATABASE_MAXCONN=int,
        CANONICAL_HOST=str,
        CANONICAL_SCHEME=str,
        COMPRESS_ASSETS=is_yesish,
        CSP_EXTRA=str,
        SENTRY_DSN=str,
        SENTRY_RERAISE=is_yesish,
        LOG_DIR=str,
        KEEP_PAYDAY_LOGS=is_yesish,
        LOGGING_LEVEL=str,
        CACHE_STATIC=is_yesish,
        CLEAN_ASSETS=is_yesish,
        RUN_CRON_JOBS=is_yesish,
        OVERRIDE_PAYDAY_CHECKS=is_yesish,
        OVERRIDE_QUERY_CACHE=is_yesish,
        GRATIPAY_BASE_URL=str,
        SECRET_FOR_GRATIPAY=str,
        INSTANCE_TYPE=str,
    )

    logging.basicConfig(level=getattr(logging, env.logging_level.upper()))

    if env.log_dir[:1] == '$':
        var_name = env.log_dir[1:]
        env.log_dir = os.environ.get(var_name)
        if env.log_dir is None:
            env.missing.append(var_name+' (referenced by LOG_DIR)')

    if env.malformed:
        plural = len(env.malformed) != 1 and 's' or ''
        print("=" * 42)
        print("Malformed environment variable%s:" % plural)
        for key, err in env.malformed:
            print("  {} ({})".format(key, err))

    if env.missing:
        plural = len(env.missing) != 1 and 's' or ''
        keys = ', '.join([key for key in env.missing])
        print("Missing envvar{}: {}.".format(plural, keys))

    return {'env': env}


def load_scss_variables(project_root):
    """Build a dict representing the `style/variables.scss` file.
    """
    # Get the names of all the variables
    with open(project_root + '/style/variables.scss') as f:
        variables = f.read()
    names = [m.group(1) for m in re.finditer(r'^\$([\w-]+):', variables, re.M)]
    # Compile a big rule that uses all the variables
    props = ''.join('-x-{0}: ${0};'.format(name) for name in names)
    css = sass.compile(string=('%s\nx { %s }' % (variables, props)))
    # Read the final values from the generated CSS
    d = dict((m.group(1), m.group(2)) for m in re.finditer(r'-x-([\w-]+): (.+?);\s', css))
    return {'scss_variables': d}


def s3(env):
    key, secret = env.aws_access_key_id, env.aws_secret_access_key
    if key and secret:
        s3 = boto3.client('s3', aws_access_key_id=key, aws_secret_access_key=secret)
    else:
        s3 = None
    return {'s3': s3}


def currency_exchange_rates(db):
    return {'currency_exchange_rates': get_currency_exchange_rates(db)}


minimal_algorithm = Algorithm(
    env,
    make_sentry_teller,
    database,
)

full_algorithm = Algorithm(
    env,
    make_sentry_teller,
    database,
    canonical,
    csp,
    app_conf,
    mail,
    billing,
    username_restrictions,
    load_i18n,
    asset_url_generator,
    accounts_elsewhere,
    load_scss_variables,
    s3,
    trusted_proxies,
    currency_exchange_rates,
)


def main():
    from os import environ
    environ['RUN_CRON_JOBS'] = 'no'
    from liberapay.main import website
    app_conf, env = website.app_conf, website.env
    if app_conf.missing or app_conf.mistyped or env.missing or env.malformed:
        raise SystemExit('The configuration is incorrect.')


if __name__ == '__main__':
    main()
