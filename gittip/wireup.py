"""Wireup
"""
import os
import sys

import aspen
import balanced
import gittip
import raven
import psycopg2
import stripe
import gittip.mixpanel
from gittip.postgres import PostgresManager
from psycopg2.extensions import cursor as RegularCursor


def canonical():
    gittip.canonical_scheme = os.environ['CANONICAL_SCHEME']
    gittip.canonical_host = os.environ['CANONICAL_HOST']


# wireup.db() should only ever be called once by the application
def db():
    dburl = os.environ['DATABASE_URL']
    maxconn = int(os.environ['DATABASE_MAXCONN'])
    gittip.db = PostgresManager(dburl, maxconn=maxconn)

    # register hstore type (but don't use RealDictCursor)
    with gittip.db.get_connection() as conn:
        curs = conn.cursor(cursor_factory=RegularCursor)
        psycopg2.extras.register_hstore(curs, globally=True, unicode=True)

    return gittip.db


def billing():
    stripe.api_key= os.environ['STRIPE_SECRET_API_KEY']
    stripe.publishable_api_key= os.environ['STRIPE_PUBLISHABLE_API_KEY']
    balanced.configure(os.environ['BALANCED_API_SECRET'])


def username_restrictions(website):
    gittip.RESTRICTED_USERNAMES = os.listdir(website.www_root)


def sentry(website):
    sentry_dsn = os.environ.get('SENTRY_DSN')
    if sentry_dsn is not None:
        sentry = raven.Client(sentry_dsn)
        def tell_sentry(request):
            cls, response = sys.exc_info()[:2]
            if cls is aspen.Response:
                if response.code < 500:
                    return

            kw = {'extra': { "filepath": request.fs
                           , "request": str(request).splitlines()
                            }}
            exc = sentry.captureException(**kw)
            ident = sentry.get_ident(exc)
            aspen.log_dammit("Exception reference: " + ident)
        website.hooks.error_early += [tell_sentry]


def mixpanel(website):
    website.mixpanel_token = os.environ['MIXPANEL_TOKEN']
    gittip.mixpanel.MIXPANEL_TOKEN = os.environ['MIXPANEL_TOKEN']

def nanswers():
    from gittip.models import participant
    participant.NANSWERS_THRESHOLD = int(os.environ['NANSWERS_THRESHOLD'])

def nmembers(website):
    from gittip.models import community
    community.NMEMBERS_THRESHOLD = int(os.environ['NMEMBERS_THRESHOLD'])
    website.NMEMBERS_THRESHOLD = community.NMEMBERS_THRESHOLD

def envvars(website):

    missing_keys = []

    def envvar(key):
        if key not in os.environ:
            missing_keys.append(key)
            return ""
        return os.environ[key].decode('ASCII')

    def is_yesish(val):
        return val.lower() in ('1', 'true', 'yes')

    website.bitbucket_consumer_key = envvar('BITBUCKET_CONSUMER_KEY')
    website.bitbucket_consumer_secret = envvar('BITBUCKET_CONSUMER_SECRET')
    website.bitbucket_callback = envvar('BITBUCKET_CALLBACK')

    website.github_client_id = envvar('GITHUB_CLIENT_ID')
    website.github_client_secret = envvar('GITHUB_CLIENT_SECRET')
    website.github_callback = envvar('GITHUB_CALLBACK')

    website.twitter_consumer_key = envvar('TWITTER_CONSUMER_KEY')
    website.twitter_consumer_secret = envvar('TWITTER_CONSUMER_SECRET')
    website.twitter_access_token = envvar('TWITTER_ACCESS_TOKEN')
    website.twitter_access_token_secret = envvar('TWITTER_ACCESS_TOKEN_SECRET')
    website.twitter_callback = envvar('TWITTER_CALLBACK')

    website.bountysource_www_host = envvar('BOUNTYSOURCE_WWW_HOST')
    website.bountysource_api_host = envvar('BOUNTYSOURCE_API_HOST')
    website.bountysource_api_secret = envvar('BOUNTYSOURCE_API_SECRET')
    website.bountysource_callback = envvar('BOUNTYSOURCE_CALLBACK')

    website.css_href = envvar('GITTIP_CSS_HREF') \
                                          .replace('%version', website.version)
    website.cache_static = is_yesish(envvar('GITTIP_CACHE_STATIC'))

    if missing_keys:
        missing_keys.sort()
        these = len(missing_keys) != 1 and 'these' or 'this'
        plural = len(missing_keys) != 1 and 's' or ''
        aspen.log_dammit("=" * 42)
        aspen.log_dammit( "Oh no! Gittip.com needs %s missing " % these
                        , "environment variable%s:" % plural
                         )
        aspen.log_dammit(" ")
        for key in missing_keys:
            aspen.log_dammit("  " + key)
        aspen.log_dammit(" ")
        aspen.log_dammit( "(Sorry, we must've started looking for "
                        , "%s since you last updated Gittip!)" % these
                         )
        aspen.log_dammit(" ")
        aspen.log_dammit("Running Gittip locally? Edit ./local.env.")
        aspen.log_dammit("Running the test suite? Edit ./tests/env.")
        aspen.log_dammit(" ")
        aspen.log_dammit("See ./default_local.env for hints.")

        aspen.log_dammit("=" * 42)
        raise SystemExit
