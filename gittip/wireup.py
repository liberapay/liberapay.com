"""Wireup
"""
import os
import sys
import time

import aspen
import balanced
import gittip
import raven
import psycopg2
import stripe
import gittip.utils.mixpanel
from gittip.models.community import Community
from gittip.models.participant import Participant
from postgres import Postgres


def canonical():
    gittip.canonical_scheme = os.environ['CANONICAL_SCHEME']
    gittip.canonical_host = os.environ['CANONICAL_HOST']


# wireup.db() should only ever be called once by the application
def db():
    dburl = os.environ['DATABASE_URL']
    maxconn = int(os.environ['DATABASE_MAXCONN'])
    db = gittip.db = Postgres(dburl, maxconn=maxconn)

    # register hstore type
    with db.get_cursor() as cursor:
        psycopg2.extras.register_hstore(cursor, globally=True, unicode=True)

    db.register_model(Community)
    db.register_model(Participant)

    return db


def billing():
    stripe.api_key= os.environ['STRIPE_SECRET_API_KEY']
    stripe.publishable_api_key= os.environ['STRIPE_PUBLISHABLE_API_KEY']
    balanced.configure(os.environ['BALANCED_API_SECRET'])


def username_restrictions(website):
    gittip.RESTRICTED_USERNAMES = os.listdir(website.www_root)


def make_sentry_teller(website):
    if not website.sentry_dsn:
        aspen.log_dammit("Won't log to Sentry (SENTRY_DSN is empty).")
        return lambda x: None

    sentry = raven.Client(website.sentry_dsn)

    def tell_sentry(request):
        cls, response = sys.exc_info()[:2]


        # Decide if we care.
        # ==================

        if cls is aspen.Response:

            if response.code < 500:

                # Only log server errors to Sentry. For responses < 500 we use
                # stream-/line-based access logging. See discussion on:

                # https://github.com/gittip/www.gittip.com/pull/1560.

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
                                   , 'url': 'https://www.gittip.com/{}/'.format(username)
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


def mixpanel(website):
    website.mixpanel_token = os.environ['MIXPANEL_TOKEN']
    gittip.utils.mixpanel.MIXPANEL_TOKEN = os.environ['MIXPANEL_TOKEN']

def nanswers():
    from gittip.models import participant
    participant.NANSWERS_THRESHOLD = int(os.environ['NANSWERS_THRESHOLD'])

def nmembers(website):
    from gittip.models import community
    community.NMEMBERS_THRESHOLD = int(os.environ['NMEMBERS_THRESHOLD'])
    website.NMEMBERS_THRESHOLD = community.NMEMBERS_THRESHOLD

def envvars(website):

    missing_keys = []
    malformed_values = []

    def envvar(key, cast=None):
        if key not in os.environ:
            missing_keys.append(key)
            return ""
        value = os.environ[key].decode('ASCII')
        if cast is not None:
            try:
                value = cast(value)
            except:
                err = str(sys.exc_info()[1])
                malformed_values.append((key, err))
                return ""
        return value

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
    website.js_src = envvar('GITTIP_JS_SRC') \
                                          .replace('%version', website.version)
    website.cache_static = is_yesish(envvar('GITTIP_CACHE_STATIC'))

    website.google_analytics_id = envvar('GOOGLE_ANALYTICS_ID')
    website.gauges_id = envvar('GAUGES_ID')
    website.sentry_dsn = envvar('SENTRY_DSN')

    website.min_threads = envvar('MIN_THREADS', int)
    website.log_busy_threads_every = envvar('LOG_BUSY_THREADS_EVERY', int)

    if malformed_values:
        malformed_values.sort()
        these = len(malformed_values) != 1 and 'these' or 'this'
        plural = len(malformed_values) != 1 and 's' or ''
        aspen.log_dammit("=" * 42)
        aspen.log_dammit( "Oh no! Gittip.com couldn't understand %s " % these
                        , "environment variable%s:" % plural
                         )
        aspen.log_dammit(" ")
        for key, err in malformed_values:
            aspen.log_dammit("  {} ({})".format(key, err))
        aspen.log_dammit(" ")
        aspen.log_dammit("See ./default_local.env for hints.")

        aspen.log_dammit("=" * 42)
        raise SystemExit

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
