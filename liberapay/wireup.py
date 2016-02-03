"""Wireup
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import atexit
import fnmatch
import os
import re
from tempfile import mkstemp

import aspen
from aspen.testing.client import Client
from babel.core import Locale
from babel.messages.pofile import read_po
from babel.numbers import parse_pattern
from environment import Environment, is_yesish
import mandrill
import raven

import liberapay
import liberapay.billing.payday
from liberapay.elsewhere import PlatformRegistry
from liberapay.elsewhere.bitbucket import Bitbucket
from liberapay.elsewhere.bountysource import Bountysource
from liberapay.elsewhere.github import GitHub
from liberapay.elsewhere.facebook import Facebook
from liberapay.elsewhere.google import Google
from liberapay.elsewhere.openstreetmap import OpenStreetMap
from liberapay.elsewhere.twitter import Twitter
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.community import Community
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.models import DB
from liberapay.utils import markdown
from liberapay.utils.emails import compile_email_spt
from liberapay.utils.http_caching import asset_etag
from liberapay.utils.i18n import (
    ALIASES, ALIASES_R, COUNTRIES, LANGUAGES_2, LOCALES,
    get_function_from_rule, make_sorted_dict
)


def canonical(env):
    liberapay.canonical_scheme = env.canonical_scheme
    liberapay.canonical_host = env.canonical_host
    liberapay.canonical_url = '%s://%s' % (env.canonical_scheme, env.canonical_host)


def db(env):
    dburl = env.database_url
    maxconn = env.database_maxconn
    db = DB(dburl, maxconn=maxconn)

    for model in (AccountElsewhere, Community, ExchangeRoute, Participant):
        db.register_model(model)
    liberapay.billing.payday.Payday.db = db

    Participant._password_rounds = env.password_rounds

    return db


def mail(env, project_root='.'):
    Participant._mailer = mandrill.Mandrill(env.mandrill_key)
    emails = {}
    emails_dir = project_root+'/emails/'
    i = len(emails_dir)
    for spt in find_files(emails_dir, '*.spt'):
        base_name = spt[i:-4]
        emails[base_name] = compile_email_spt(spt)
    Participant._emails = emails


def billing(env):
    from mangopaysdk.configuration import Configuration
    Configuration.BaseUrl = env.mangopay_base_url
    Configuration.ClientID = env.mangopay_client_id
    Configuration.ClientPassword = env.mangopay_client_password
    Configuration.SSLVerification = True


def username_restrictions(website):
    liberapay.RESTRICTED_USERNAMES = os.listdir(website.www_root)


def make_sentry_teller(env):
    if not env.sentry_dsn:
        aspen.log_dammit("Won't log to Sentry (SENTRY_DSN is empty).")
        def noop(*a, **kw):
            pass
        Participant._tell_sentry = noop
        return noop

    sentry = raven.Client(env.sentry_dsn)

    def tell_sentry(exception, state):

        # Decide if we care.
        # ==================

        if isinstance(exception, aspen.Response):

            if exception.code < 500:

                # Only log server errors to Sentry. For responses < 500 we use
                # stream-/line-based access logging. See discussion on:

                # https://github.com/liberapay/liberapay.com/pull/1560.

                return


        # Find a user.
        # ============
        # | is disallowed in usernames, so we can use it here to indicate
        # situations in which we can't get a username.

        user = state.get('user')
        user_id = 'n/a'
        if user is None:
            username = '| no user'
        else:
            is_anon = getattr(user, 'ANON', None)
            if is_anon is None:
                username = '| no ANON'
            elif is_anon:
                username = '| anonymous'
            else:
                username = getattr(user, 'username', None)
                if username is None:
                    username = '| no username'
                else:
                    user_id = user.id
                    user = { 'id': user_id
                           , 'is_admin': user.is_admin
                           , 'is_suspicious': user.is_suspicious
                           , 'join_time': user.join_time.isoformat()
                           , 'url': 'https://liberapay.com/{}/'.format(username)
                            }


        # Fire off a Sentry call.
        # =======================

        dispatch_result = state.get('dispatch_result')
        request = state.get('request')
        tags = { 'username': username
               , 'user_id': user_id
                }
        extra = { 'filepath': getattr(dispatch_result, 'match', None)
                , 'request': str(request).splitlines()
                , 'user': user
                 }
        result = sentry.captureException(tags=tags, extra=extra)


        # Emit a reference string to stdout.
        # ==================================

        ident = sentry.get_ident(result)
        aspen.log_dammit('Exception reference: ' + ident)

    Participant._tell_sentry = tell_sentry
    return tell_sentry


class BadEnvironment(SystemExit):
    pass


def accounts_elsewhere(website, env):

    twitter = Twitter(
        env.twitter_consumer_key,
        env.twitter_consumer_secret,
        env.twitter_callback,
    )
    facebook = Facebook(
        env.facebook_app_id,
        env.facebook_app_secret,
        env.facebook_callback,
    )
    github = GitHub(
        env.github_client_id,
        env.github_client_secret,
        env.github_callback,
    )
    google = Google(
        env.google_client_id,
        env.google_client_secret,
        env.google_callback,
    )
    bitbucket = Bitbucket(
        env.bitbucket_consumer_key,
        env.bitbucket_consumer_secret,
        env.bitbucket_callback,
    )
    openstreetmap = OpenStreetMap(
        env.openstreetmap_consumer_key,
        env.openstreetmap_consumer_secret,
        env.openstreetmap_callback,
        env.openstreetmap_api_url,
        env.openstreetmap_auth_url,
    )
    bountysource = Bountysource(
        None,
        env.bountysource_api_secret,
        env.bountysource_callback,
        env.bountysource_api_host,
        env.bountysource_www_host,
    )

    platforms = [twitter, github, facebook, google, bitbucket, openstreetmap, bountysource]
    platforms = [p for p in platforms if p.api_secret]
    website.platforms = AccountElsewhere.platforms = PlatformRegistry(platforms)

    friends_platforms = [p for p in website.platforms if getattr(p, 'api_friends_path', None)]
    website.friends_platforms = PlatformRegistry(friends_platforms)

    for platform in platforms:
        platform.icon = website.asset('platforms/%s.16.png' % platform.name)
        platform.logo = website.asset('platforms/%s.png' % platform.name)


def find_files(directory, pattern):
    for root, dirs, files in os.walk(directory):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(root, filename)


def compile_assets(website):
    client = Client(website.www_root, website.project_root)
    client._website = website
    for spt in find_files(website.www_root+'/assets/', '*.spt'):
        filepath = spt[:-4]                         # /path/to/www/assets/foo.css
        urlpath = spt[spt.rfind('/assets/'):-4]     # /assets/foo.css
        try:
            # Remove any existing compiled asset, so we can access the dynamic
            # one instead (Aspen prefers foo.css over foo.css.spt).
            os.unlink(filepath)
        except:
            pass
        content = client.GET(urlpath).body
        tmpfd, tmpfpath = mkstemp(dir='.')
        os.write(tmpfd, content)
        os.close(tmpfd)
        os.rename(tmpfpath, filepath)
    atexit.register(lambda: clean_assets(website.www_root))


def clean_assets(www_root):
    for spt in find_files(www_root+'/assets/', '*.spt'):
        try:
            os.unlink(spt[:-4])
        except:
            pass


def load_i18n(website):
    # Load the locales
    localeDir = os.path.join(website.project_root, 'i18n', 'core')
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
                try:
                    l.countries = make_sorted_dict(COUNTRIES, l.territories)
                except KeyError:
                    l.countries = COUNTRIES
                try:
                    l.languages_2 = make_sorted_dict(LANGUAGES_2, l.languages)
                except KeyError:
                    l.languages_2 = LANGUAGES_2
        except Exception as e:
            website.tell_sentry(e, {})

    # Add aliases
    for k, v in list(locales.items()):
        locales.setdefault(ALIASES.get(k, k), v)
        locales.setdefault(ALIASES_R.get(k, k), v)
    for k, v in list(locales.items()):
        locales.setdefault(k.split('_', 1)[0], v)

    # Patch the locales to look less formal
    locales['fr'].currency_formats[None] = parse_pattern('#,##0.00\u202f\xa4')
    locales['fr'].currency_symbols['USD'] = '$'

    # Load the markdown files
    docs = website.docs = {}
    heading_re = re.compile(r'^(#+ )', re.M)
    for path in find_files(os.path.join(website.project_root, 'i18n'), '*.md'):
        d, b = os.path.split(path)
        doc = os.path.basename(d)
        lang = b[:-3]
        with open(path, 'rb') as f:
            md = f.read().decode('utf8')
            if md.startswith('# '):
                md = '\n'.join(md.split('\n')[1:]).strip()
                md = heading_re.sub(r'##\1', md)
            docs.setdefault(doc, {}).__setitem__(lang, markdown.render(md))


def other_stuff(website, env):
    if env.cache_static:
        def asset(path):
            fspath = website.www_root+'/assets/'+path
            etag = ''
            try:
                etag = asset_etag(fspath)
            except Exception as e:
                website.tell_sentry(e, {})
            return env.asset_url+path+(etag and '?etag='+etag)
        website.asset = asset
        compile_assets(website)
    else:
        website.asset = lambda path: env.asset_url+path
        clean_assets(website.www_root)

    website.log_metrics = env.log_metrics


def env():
    env = Environment(
        ASPEN_PROJECT_ROOT              = str,
        DATABASE_URL                    = str,
        DATABASE_MAXCONN                = int,
        CANONICAL_HOST                  = str,
        CANONICAL_SCHEME                = str,
        ASSET_URL                       = str,
        CACHE_STATIC                    = is_yesish,
        COMPRESS_ASSETS                 = is_yesish,
        PASSWORD_ROUNDS                 = int,
        MANGOPAY_BASE_URL               = str,
        MANGOPAY_CLIENT_ID              = str,
        MANGOPAY_CLIENT_PASSWORD        = str,
        GITHUB_CLIENT_ID                = str,
        GITHUB_CLIENT_SECRET            = str,
        GITHUB_CALLBACK                 = str,
        BITBUCKET_CONSUMER_KEY          = str,
        BITBUCKET_CONSUMER_SECRET       = str,
        BITBUCKET_CALLBACK              = str,
        TWITTER_CONSUMER_KEY            = str,
        TWITTER_CONSUMER_SECRET         = str,
        TWITTER_CALLBACK                = str,
        FACEBOOK_APP_ID                 = str,
        FACEBOOK_APP_SECRET             = str,
        FACEBOOK_CALLBACK               = str,
        GOOGLE_CLIENT_ID                = str,
        GOOGLE_CLIENT_SECRET            = str,
        GOOGLE_CALLBACK                 = str,
        BOUNTYSOURCE_API_SECRET         = str,
        BOUNTYSOURCE_CALLBACK           = str,
        BOUNTYSOURCE_API_HOST           = str,
        BOUNTYSOURCE_WWW_HOST           = str,
        OPENSTREETMAP_CONSUMER_KEY      = str,
        OPENSTREETMAP_CONSUMER_SECRET   = str,
        OPENSTREETMAP_CALLBACK          = str,
        OPENSTREETMAP_API_URL           = str,
        OPENSTREETMAP_AUTH_URL          = str,
        UPDATE_GLOBAL_STATS_EVERY       = int,
        CHECK_DB_EVERY                  = int,
        DEQUEUE_EMAILS_EVERY            = int,
        SENTRY_DSN                      = str,
        LOG_METRICS                     = is_yesish,
        MANDRILL_KEY                    = str,
        GUNICORN_OPTS                   = str,
    )


    # Error Checking
    # ==============

    if env.malformed:
        plural = len(env.malformed) != 1 and 's' or ''
        aspen.log_dammit("=" * 42)
        aspen.log_dammit("Malformed environment variable%s:" % plural)
        aspen.log_dammit(" ")
        for key, err in env.malformed:
            aspen.log_dammit("  {} ({})".format(key, err))

        keys = ', '.join([key for key in env.malformed])
        raise BadEnvironment("Malformed envvar{}: {}.".format(plural, keys))

    if env.missing:
        plural = len(env.missing) != 1 and 's' or ''
        aspen.log_dammit("=" * 42)
        aspen.log_dammit("Missing environment variable%s:" % plural)
        aspen.log_dammit(" ")
        for key in env.missing:
            aspen.log_dammit("  " + key)

        keys = ', '.join([key for key in env.missing])
        raise BadEnvironment("Missing envvar{}: {}.".format(plural, keys))

    return env


if __name__ == '__main__':
    env()
