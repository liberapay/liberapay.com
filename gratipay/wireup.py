"""Wireup
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import fnmatch
import os
from tempfile import mkstemp

import aspen
from aspen.testing.client import Client
from babel.core import Locale
from babel.messages.pofile import Catalog, read_po
from babel.numbers import parse_pattern
import balanced
import gratipay
import gratipay.billing.payday
import raven
import mandrill
from environment import Environment, is_yesish
from gratipay.elsewhere import PlatformRegistry
from gratipay.elsewhere.bitbucket import Bitbucket
from gratipay.elsewhere.bountysource import Bountysource
from gratipay.elsewhere.github import GitHub
from gratipay.elsewhere.facebook import Facebook
from gratipay.elsewhere.google import Google
from gratipay.elsewhere.openstreetmap import OpenStreetMap
from gratipay.elsewhere.twitter import Twitter
from gratipay.elsewhere.venmo import Venmo
from gratipay.models.account_elsewhere import AccountElsewhere
from gratipay.models.community import Community
from gratipay.models.participant import Participant
from gratipay.models.email_address_with_confirmation import EmailAddressWithConfirmation
from gratipay.models import GratipayDB
from gratipay.utils import COUNTRIES, COUNTRIES_MAP
from gratipay.utils.cache_static import asset_etag
from gratipay.utils.i18n import ALIASES, ALIASES_R, get_function_from_rule, strip_accents

def canonical(env):
    gratipay.canonical_scheme = env.canonical_scheme
    gratipay.canonical_host = env.canonical_host


def db(env):
    dburl = env.database_url
    maxconn = env.database_maxconn
    db = GratipayDB(dburl, maxconn=maxconn)

    db.register_model(Community)
    db.register_model(AccountElsewhere)
    db.register_model(Participant)
    db.register_model(EmailAddressWithConfirmation)
    gratipay.billing.payday.Payday.db = db

    return db

def mail(env):
    mandrill_client = mandrill.Mandrill(env.mandrill_key)
    return mandrill_client

def billing(env):
    balanced.configure(env.balanced_api_secret)


def username_restrictions(website):
    if not hasattr(gratipay, 'RESTRICTED_USERNAMES'):
        gratipay.RESTRICTED_USERNAMES = os.listdir(website.www_root)


def make_sentry_teller(env):
    if not env.sentry_dsn:
        aspen.log_dammit("Won't log to Sentry (SENTRY_DSN is empty).")
        def noop(exception, request=None):
            pass
        return noop

    sentry = raven.Client(env.sentry_dsn)

    def tell_sentry(exception, request=None):

        # Decide if we care.
        # ==================

        if isinstance(exception, aspen.Response):

            if exception.code < 500:

                # Only log server errors to Sentry. For responses < 500 we use
                # stream-/line-based access logging. See discussion on:

                # https://github.com/gratipay/gratipay.com/pull/1560.

                return


        # Find a user.
        # ============
        # | is disallowed in usernames, so we can use it here to indicate
        # situations in which we can't get a username.

        request_context = getattr(request, 'context', None)
        user = {}
        user_id = 'n/a'
        if request_context is None:
            username = '| no context'
        else:
            user = request.context.get('user', None)
            if user is None:
                username = '| no user'
            else:
                is_anon = getattr(user, 'ANON', None)
                if is_anon is None:
                    username = '| no ANON'
                elif is_anon:
                    username = '| anonymous'
                else:
                    participant = getattr(user, 'participant', None)
                    if participant is None:
                        username = '| no participant'
                    else:
                        username = getattr(user.participant, 'username', None)
                        if username is None:
                            username = '| no username'
                        else:
                            user_id = user.participant.id
                            username = username.encode('utf8')
                            user = { 'id': user_id
                                   , 'is_admin': user.participant.is_admin
                                   , 'is_suspicious': user.participant.is_suspicious
                                   , 'claimed_time': user.participant.claimed_time.isoformat()
                                   , 'url': 'https://gratipay.com/{}/'.format(username)
                                    }


        # Fire off a Sentry call.
        # =======================

        tags = { 'username': username
               , 'user_id': user_id
                }
        extra = { 'filepath': getattr(request, 'fs', None)
                , 'request': str(request).splitlines()
                , 'user': user
                 }
        result = sentry.captureException(tags=tags, extra=extra)


        # Emit a reference string to stdout.
        # ==================================

        ident = sentry.get_ident(result)
        aspen.log_dammit('Exception reference: ' + ident)

    return tell_sentry


def nanswers(env):
    from gratipay.models import participant
    participant.NANSWERS_THRESHOLD = env.nanswers_threshold


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
    venmo = Venmo(
        env.venmo_client_id,
        env.venmo_client_secret,
        env.venmo_callback,
    )

    signin_platforms = [twitter, github, facebook, google, bitbucket, openstreetmap]
    website.signin_platforms = PlatformRegistry(signin_platforms)
    AccountElsewhere.signin_platforms_names = tuple(p.name for p in signin_platforms)

    # For displaying "Connected Accounts"
    website.social_profiles = [twitter, github, facebook, google, bitbucket, openstreetmap, bountysource]

    all_platforms = signin_platforms + [bountysource, venmo]
    website.platforms = AccountElsewhere.platforms = PlatformRegistry(all_platforms)

    for platform in all_platforms:
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


def clean_assets(website):
    for spt in find_files(website.www_root+'/assets/', '*.spt'):
        try:
            os.unlink(spt[:-4])
        except:
            pass


def load_i18n(website):
    # Load the locales
    key = lambda t: strip_accents(t[1])
    localeDir = os.path.join(website.project_root, 'i18n', 'core')
    locales = website.locales = {}
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
                    l.countries_map = {k: l.territories[k] for k in COUNTRIES_MAP}
                    l.countries = sorted(l.countries_map.items(), key=key)
                except KeyError:
                    l.countries_map = COUNTRIES_MAP
                    l.countries = COUNTRIES
        except Exception as e:
            website.tell_sentry(e)

    # Add the default English locale
    locale_en = website.locale_en = locales['en'] = Locale('en')
    locale_en.catalog = Catalog('en')
    locale_en.catalog.plural_func = lambda n: n != 1
    locale_en.countries = COUNTRIES
    locale_en.countries_map = COUNTRIES_MAP

    # Add aliases
    for k, v in list(locales.items()):
        locales.setdefault(ALIASES.get(k, k), v)
        locales.setdefault(ALIASES_R.get(k, k), v)
    for k, v in list(locales.items()):
        locales.setdefault(k.split('_', 1)[0], v)

    # Patch the locales to look less formal
    locales['fr'].currency_formats[None] = parse_pattern('#,##0.00\u202f\xa4')
    locales['fr'].currency_symbols['USD'] = '$'


def other_stuff(website, env):
    website.cache_static = env.gratipay_cache_static
    website.compress_assets = env.gratipay_compress_assets

    if website.cache_static:
        def asset(path):
            fspath = website.www_root+'/assets/'+path
            etag = ''
            try:
                etag = asset_etag(fspath)
            except Exception as e:
                website.tell_sentry(e)
            return env.gratipay_asset_url+path+(etag and '?etag='+etag)
        website.asset = asset
        compile_assets(website)
    else:
        website.asset = lambda path: env.gratipay_asset_url+path
        clean_assets(website)

    website.google_analytics_id = env.google_analytics_id
    website.optimizely_id = env.optimizely_id

    website.log_metrics = env.log_metrics


def env():
    env = Environment(
        DATABASE_URL                    = unicode,
        CANONICAL_HOST                  = unicode,
        CANONICAL_SCHEME                = unicode,
        DATABASE_MAXCONN                = int,
        GRATIPAY_ASSET_URL              = unicode,
        GRATIPAY_CACHE_STATIC           = is_yesish,
        GRATIPAY_COMPRESS_ASSETS        = is_yesish,
        BALANCED_API_SECRET             = unicode,
        GITHUB_CLIENT_ID                = unicode,
        GITHUB_CLIENT_SECRET            = unicode,
        GITHUB_CALLBACK                 = unicode,
        BITBUCKET_CONSUMER_KEY          = unicode,
        BITBUCKET_CONSUMER_SECRET       = unicode,
        BITBUCKET_CALLBACK              = unicode,
        TWITTER_CONSUMER_KEY            = unicode,
        TWITTER_CONSUMER_SECRET         = unicode,
        TWITTER_CALLBACK                = unicode,
        FACEBOOK_APP_ID                 = unicode,
        FACEBOOK_APP_SECRET             = unicode,
        FACEBOOK_CALLBACK               = unicode,
        GOOGLE_CLIENT_ID                = unicode,
        GOOGLE_CLIENT_SECRET            = unicode,
        GOOGLE_CALLBACK                 = unicode,
        BOUNTYSOURCE_API_SECRET         = unicode,
        BOUNTYSOURCE_CALLBACK           = unicode,
        BOUNTYSOURCE_API_HOST           = unicode,
        BOUNTYSOURCE_WWW_HOST           = unicode,
        VENMO_CLIENT_ID                 = unicode,
        VENMO_CLIENT_SECRET             = unicode,
        VENMO_CALLBACK                  = unicode,
        OPENSTREETMAP_CONSUMER_KEY      = unicode,
        OPENSTREETMAP_CONSUMER_SECRET   = unicode,
        OPENSTREETMAP_CALLBACK          = unicode,
        OPENSTREETMAP_API_URL           = unicode,
        OPENSTREETMAP_AUTH_URL          = unicode,
        NANSWERS_THRESHOLD              = int,
        UPDATE_GLOBAL_STATS_EVERY       = int,
        CHECK_DB_EVERY                  = int,
        GOOGLE_ANALYTICS_ID             = unicode,
        OPTIMIZELY_ID                   = unicode,
        SENTRY_DSN                      = unicode,
        LOG_METRICS                     = is_yesish,
        MANDRILL_KEY                    = unicode,
        RAISE_CARD_EXPIRATION           = is_yesish,

        # This is used in our Procfile. (PORT is also used but is provided by
        # Heroku; we don't set it ourselves in our app config.)
        GUNICORN_OPTS                   = unicode,
    )


    # Error Checking
    # ==============

    if env.malformed:
        these = len(env.malformed) != 1 and 'these' or 'this'
        plural = len(env.malformed) != 1 and 's' or ''
        aspen.log_dammit("=" * 42)
        aspen.log_dammit( "Oh no! Gratipay.com couldn't understand %s " % these
                        , "environment variable%s:" % plural
                         )
        aspen.log_dammit(" ")
        for key, err in env.malformed:
            aspen.log_dammit("  {} ({})".format(key, err))
        aspen.log_dammit(" ")
        aspen.log_dammit("See ./default_local.env for hints.")

        aspen.log_dammit("=" * 42)
        keys = ', '.join([key for key in env.malformed])
        raise BadEnvironment("Malformed envvar{}: {}.".format(plural, keys))

    if env.missing:
        these = len(env.missing) != 1 and 'these' or 'this'
        plural = len(env.missing) != 1 and 's' or ''
        aspen.log_dammit("=" * 42)
        aspen.log_dammit( "Oh no! Gratipay.com needs %s missing " % these
                        , "environment variable%s:" % plural
                         )
        aspen.log_dammit(" ")
        for key in env.missing:
            aspen.log_dammit("  " + key)
        aspen.log_dammit(" ")
        aspen.log_dammit( "(Sorry, we must've started looking for "
                        , "%s since you last updated Gratipay!)" % these
                         )
        aspen.log_dammit(" ")
        aspen.log_dammit("Running Gratipay locally? Edit ./local.env.")
        aspen.log_dammit("Running the test suite? Edit ./tests/env.")
        aspen.log_dammit(" ")
        aspen.log_dammit("See ./default_local.env for hints.")

        aspen.log_dammit("=" * 42)
        keys = ', '.join([key for key in env.missing])
        raise BadEnvironment("Missing envvar{}: {}.".format(plural, keys))

    return env


if __name__ == '__main__':
    env()
