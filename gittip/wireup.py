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


def sentry(website):
    if not website.sentry_dsn:
        aspen.log_dammit("Won't log to Sentry (SENTRY_DSN is empty).")
        return

    sentry = raven.Client(website.sentry_dsn)

    def tell_sentry(request):
        cls, response = sys.exc_info()[:2]


        # Tag by HTTP response code.
        # ==========================

        if cls is aspen.Response:
            response_code = response.code
        else:

            # Any non-Response exception we see here is going to result in
            # a 500 to the user, so let's report it as that. See discussion
            # at:

            # https://github.com/gittip/www.gittip.com/pull/1560#issuecomment-25913549

            response_code = 500


        # Tag by username.
        # ================
        # | is disallowed in usernames, so we can use it here to indicate
        # situations in which we can't get a username.

        request_context = getattr(request, 'context', None)
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


        # Build the message.
        # ==================

        tags = { 'response code': response_code
               , 'username': username
                }
        extra = { 'filepath': request.fs
                , 'request': str(request).splitlines()
                 }
        data = sentry.build_msg( 'raven.events.Exception'
                               , exc_info=None
                               , tags=tags
                               , extra=extra
                                )

        # Set level.
        # ==========
        # Sentry takes an int for level, which it converts to a string and uses
        # as a tag in the UI and also (for now) to color-code events. The
        # Exception event handler hard-wires level to 40 (logging.ERROR). We
        # want to vary it based on the response code, but we don't have a hook
        # to override it if we use sentry.captureException, so we've unrolled
        # that here.

        data['level'] = (response_code // 100) * 10


        # Send it off.
        # ============

        sentry.send(**data)  # HTTP under here


        # Emit a single reference string on stdout.
        # =========================================
        # We don't log any tracebacks.

        ident = sentry.get_ident((data['event_id'], data['checksum']))
        aspen.log_dammit('Exception reference: ' + ident)


    website.hooks.error_early += [tell_sentry]


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
    website.js_src = envvar('GITTIP_JS_SRC') \
                                          .replace('%version', website.version)
    website.cache_static = is_yesish(envvar('GITTIP_CACHE_STATIC'))

    website.google_analytics_id = envvar('GOOGLE_ANALYTICS_ID')
    website.gauges_id = envvar('GAUGES_ID')
    website.sentry_dsn = envvar('SENTRY_DSN')

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
