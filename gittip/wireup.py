"""Wireup
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

import aspen
import balanced
import gittip
import raven
import stripe
from gittip.elsewhere import PlatformRegistry
from gittip.elsewhere.bitbucket import Bitbucket
from gittip.elsewhere.bountysource import Bountysource
from gittip.elsewhere.github import GitHub
from gittip.elsewhere.openstreetmap import OpenStreetMap
from gittip.elsewhere.twitter import Twitter
from gittip.elsewhere.venmo import Venmo
from gittip.models.account_elsewhere import AccountElsewhere
from gittip.models.community import Community
from gittip.models.participant import Participant
from gittip.models import GittipDB


def canonical():
    gittip.canonical_scheme = os.environ['CANONICAL_SCHEME']
    gittip.canonical_host = os.environ['CANONICAL_HOST']


def db():
    dburl = os.environ['DATABASE_URL']
    maxconn = int(os.environ['DATABASE_MAXCONN'])
    db = GittipDB(dburl, maxconn=maxconn)

    db.register_model(Community)
    db.register_model(AccountElsewhere)
    db.register_model(Participant)

    return db


def billing():
    stripe.api_key= os.environ['STRIPE_SECRET_API_KEY']
    stripe.publishable_api_key= os.environ['STRIPE_PUBLISHABLE_API_KEY']
    balanced.configure(os.environ['BALANCED_API_SECRET'])


def username_restrictions(website):
    if not hasattr(gittip, 'RESTRICTED_USERNAMES'):
        gittip.RESTRICTED_USERNAMES = os.listdir(website.www_root)


def make_sentry_teller(website):
    if not website.sentry_dsn:
        aspen.log_dammit("Won't log to Sentry (SENTRY_DSN is empty).")
        def noop(exception, request=None):
            pass
        return noop

    sentry = raven.Client(website.sentry_dsn)

    def tell_sentry(exception, request=None):

        # Decide if we care.
        # ==================

        if isinstance(exception, aspen.Response):

            if exception.code < 500:

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


def nanswers():
    from gittip.models import participant
    participant.NANSWERS_THRESHOLD = int(os.environ['NANSWERS_THRESHOLD'])


class BadEnvironment(SystemExit):
    pass


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


    # Accounts Elsewhere
    # ==================

    twitter = Twitter(
        website.db,
        envvar('TWITTER_CONSUMER_KEY'),
        envvar('TWITTER_CONSUMER_SECRET'),
        envvar('TWITTER_CALLBACK'),
    )
    github = GitHub(
        website.db,
        envvar('GITHUB_CLIENT_ID'),
        envvar('GITHUB_CLIENT_SECRET'),
        envvar('GITHUB_CALLBACK'),
    )
    bitbucket = Bitbucket(
        website.db,
        envvar('BITBUCKET_CONSUMER_KEY'),
        envvar('BITBUCKET_CONSUMER_SECRET'),
        envvar('BITBUCKET_CALLBACK'),
    )
    openstreetmap = OpenStreetMap(
        website.db,
        envvar('OPENSTREETMAP_CONSUMER_KEY'),
        envvar('OPENSTREETMAP_CONSUMER_SECRET'),
        envvar('OPENSTREETMAP_CALLBACK'),
        envvar('OPENSTREETMAP_API_URL'),
        envvar('OPENSTREETMAP_AUTH_URL'),
    )
    bountysource = Bountysource(
        website.db,
        None,
        envvar('BOUNTYSOURCE_API_SECRET'),
        envvar('BOUNTYSOURCE_CALLBACK'),
        envvar('BOUNTYSOURCE_API_HOST'),
        envvar('BOUNTYSOURCE_WWW_HOST'),
    )
    venmo = Venmo(
        website.db,
        envvar('VENMO_CLIENT_ID'),
        envvar('VENMO_CLIENT_SECRET'),
        envvar('VENMO_CALLBACK'),
    )

    signin_platforms = [twitter, github, bitbucket, openstreetmap]
    website.signin_platforms = PlatformRegistry(signin_platforms)
    AccountElsewhere.signin_platforms_names = tuple(p.name for p in signin_platforms)

    # For displaying "Connected Accounts"
    website.social_profiles = [twitter, github, bitbucket, openstreetmap, bountysource]

    all_platforms = signin_platforms + [bountysource, venmo]
    website.platforms = AccountElsewhere.platforms = PlatformRegistry(all_platforms)


    # Other Stuff
    # ===========

    website.asset_version_url = envvar('GITTIP_ASSET_VERSION_URL') \
                                      .replace('%version', website.version)
    website.asset_url = envvar('GITTIP_ASSET_URL')
    website.cache_static = is_yesish(envvar('GITTIP_CACHE_STATIC'))
    website.compress_assets = is_yesish(envvar('GITTIP_COMPRESS_ASSETS'))

    website.google_analytics_id = envvar('GOOGLE_ANALYTICS_ID')
    website.sentry_dsn = envvar('SENTRY_DSN')

    website.min_threads = envvar('MIN_THREADS', int)
    website.log_busy_threads_every = envvar('LOG_BUSY_THREADS_EVERY', int)
    website.log_metrics = is_yesish(envvar('LOG_METRICS'))


    # Error Checking
    # ==============

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
        keys = ', '.join([key for key in malformed_values])
        raise BadEnvironment("Malformed envvar{}: {}.".format(plural, keys))

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
        keys = ', '.join([key for key in missing_keys])
        raise BadEnvironment("Missing envvar{}: {}.".format(plural, keys))
