"""This subpackage contains functionality for working with accounts elsewhere.
"""
from __future__ import print_function, unicode_literals

from collections import OrderedDict
from urlparse import parse_qs

from aspen import json, log, Response, resources
from aspen.utils import typecheck
from psycopg2 import IntegrityError
import requests
from requests_oauthlib import OAuth1

import gittip
from gittip.exceptions import ProblemChangingUsername, UnknownPlatform
from gittip.models._mixin_elsewhere import NeedConfirmation
from gittip.models.account_elsewhere import AccountElsewhere
from gittip.utils.username import reserve_a_random_username

ACTIONS = ['opt-in', 'connect', 'lock', 'unlock']


# Exceptions
# ==========

class UnknownAccountElsewhere(Exception):
    pass

class BadAccountElsewhereSubclass(Exception):
    def __str__(self):
        return "The Platform subclass {} specifies an account_elsewhere_subclass that " \
               "doesn't subclass AccountElsewhere.".format(self.args[0])

class MissingAttributes(Exception):
    def __str__(self):
        return "The Platform subclass {} is missing: {}."\
                .format(self.args[0], ', '.join(self.args[1]))


# Platform Objects
# ================

class PlatformRegistry(object):
    """Registry of platforms we support connecting to your Gittip account.
    """

    def __init__(self, db):
        self.db = db

    def get(self, name, default=None):
        return getattr(self, name, default)

    def __getitem__(self, name):
        platform = self.get(name)
        if platform is None:
            raise KeyError(name)
        return platform

    def register(self, *Platforms):
        for Platform in Platforms:
            platform = Platform(self.db)
            self.__dict__[platform.name] = platform
            AccountElsewhere.subclasses[platform.name] = platform.account_elsewhere_subclass


class Platform(object):

    def __init__(self, db):
        self.db = db

        # Make sure the subclass was implemented properly.
        # ================================================

        expected_attrs = ( 'account_elsewhere_subclass'
                         , 'get_user_info'
                         , 'name'
                         , 'username_key'
                         , 'user_id_key'
                          )
        missing_attrs = []
        for attr in expected_attrs:
            if not hasattr(self, attr):
                missing_attrs.append(attr)
        if missing_attrs:
            raise MissingAttributes(self.__class__.__name__, missing_attrs)

        if not issubclass(self.account_elsewhere_subclass, AccountElsewhere):
            raise BadAccountElsewhereSubclass(self.account_elsewhere_subclass)

        return output

    def get_account(self, username):
        """Given a username on the other platform, return an AccountElsewhere object.
        """
        try:
            out = self.get_account_from_db(username)
        except UnknownAccountElsewhere:
            out = self.get_account_from_api(username)
        return out

    def get_account_from_db(self, username):
        """Given a username on the other platform, return an AccountElsewhere object.

        If the account elsewhere is unknown to us, we raise UnknownAccountElsewhere.

        """
        return self.db.one("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform=%s
               AND user_info->%s = %s

        """, (self.name, self.username_key, username), default=UnknownAccountElsewhere)

    def get_account_from_api(self, username):
        """Given a username on the other platform, return an AccountElsewhere object.

        This method always hits the API and updates our database.

        """
        user_id, user_info = self._get_account_from_api(username)
        return self.upsert(user_id, user_info)

    def _get_account_from_api(self, username):
        # Factored out so we can call upsert without hitting API for testing.
        user_info = self.get_user_info(username)
        user_id = unicode(user_info[self.user_id_key])  # If this is KeyError, then what?
        return user_id, user_info

    def upsert(self, user_id, user_info):
        """Given a unicode and a dict, dance with our db and return an AccountElsewhere.
        """
        typecheck(user_id, unicode, user_info, dict)

        # Insert the account if needed.
        # =============================
        # Do this with a transaction so that if the insert fails, the
        # participant we reserved for them is rolled back as well.
        try:
            with self.db.get_cursor() as cursor:
                random_username = reserve_a_random_username(cursor)
                cursor.execute( "INSERT INTO elsewhere "
                                "(platform, user_id, participant) "
                                "VALUES (%s, %s, %s)"
                              , (self.name, user_id, random_username)
                               )
        except IntegrityError:
            # We have a db-level uniqueness constraint on (platform, user_id)
            pass

        # Update their user_info.
        # =======================
        # Cast everything to unicode, because (I believe) hstore can take any
        # type of value, but psycopg2 can't.
        #
        #   https://postgres.heroku.com/blog/past/2012/3/14/introducing_keyvalue_data_storage_in_heroku_postgres/
        #   http://initd.org/psycopg/docs/extras.html#hstore-data-type
        #
        # XXX This clobbers things, of course, such as booleans. See
        # /on/bitbucket/%username/index.html
        for k, v in user_info.items():
            user_info[k] = unicode(v)

        username = self.db.one("""

            UPDATE elsewhere
               SET user_info=%s
             WHERE platform=%s AND user_id=%s
         RETURNING user_info->%s AS username

        """, (user_info, self.name, user_id, self.username_key))

        # Now delegate to get_account_from_db
        return self.get_account_from_db(username)

    def resolve(self, username):
        """Given a username elsewhere, return a username here.
        """
        typecheck(username, unicode)
        participant = self.db.one("""

            SELECT participant
              FROM elsewhere
             WHERE platform=%s
               AND user_info->%s = %s

        """, (self.name, self.username_key, username,))
        # XXX Do we want a uniqueness constraint on $username_key? Can we do that?

        if participant is None:
            raise Exception( "User %s on %s isn't known to us."
                           % (username, self.platform)
                            )
        return participant

    def user_action(self, request, website, user, then, action, user_info):
        cookie = request.headers.cookie

        # Make sure we have a Platform username.
        username = user_info.get(self.username_key)
        if username is None:
            log(u"We got a user_info from %s with no username (%s) [%s, %s]"
                % (self.name, self.username_key, action, then))
            raise Response(400)

        # Do something.
        log(u"%s wants to %s" % (username, action))

        account = self.get_account_from_api(username)

        if action == 'opt-in':      # opt in
            # set 'user' to give them a session :/
            user, newly_claimed = account.opt_in(username)
            del account
        elif action == 'connect':   # connect
            try:
                user.participant.take_over(account)
            except NeedConfirmation, obstacles:

                # XXX Eep! Internal redirect! Really?!
                request.internally_redirected_from = request.fs
                request.fs = website.www_root + '/on/confirm.html.spt'
                request.resource = resources.get(request)

                raise request.resource.respond(request)
            else:
                del account
        else:                       # lock or unlock
            if then != username:

                # The user could spoof `then' to match their username, but the most
                # they can do is lock/unlock their own Platform account in a convoluted
                # way.

                then = u'/on/%s/%s/lock-fail.html' % (self.name, then)

            else:

                # Associate the Platform username with a randomly-named, unclaimed
                # Gittip participant.

                assert account.participant != username, username # sanity check
                account.set_is_locked(action == 'lock')
                del account

        if then == u'':
            then = u'/%s/' % user.participant.username
        if not then.startswith(u'/'):
            # Interpret it as a Platform username.
            then = u'/on/%s/%s/' % (self.name, then)
        return then, user


class PlatformOAuth1(Platform):

    def get_oauth_init_url(self, redirect_uri, qs, website):
        oauth_hook = OAuth1(
            getattr(website, '%s_consumer_key' % self.name),
            getattr(website, '%s_consumer_secret' % self.name),
        )

        response = requests.post(
            "%s/oauth/request_token" % self.api_url,
            data={'oauth_callback': redirect_uri},
            auth=oauth_hook,
        )

        assert response.status_code == 200, response.status_code  # safety check

        reply = parse_qs(response.text)

        token = reply['oauth_token'][0]
        secret = reply['oauth_token_secret'][0]
        assert reply['oauth_callback_confirmed'][0] == "true"  # sanity check

        action = qs.get('action', 'opt-in')
        then = qs.get('then', '')
        website.oauth_cache = {}  # XXX What happens to someone who was half-authed
                                  # when we bounced the server?
        website.oauth_cache[token] = (secret, action, then)

        url = "%s/oauth/authenticate?oauth_token=%s"
        return url % (self.api_url, token)

    def handle_oauth_callback(self, request, website, user):
        qs = request.line.uri.querystring

        if 'denied' in qs or not ('oauth_token' in qs and 'oauth_verifier' in qs):
            raise Response(403)

        token = qs['oauth_token']
        try:
            secret, action, then = website.oauth_cache.pop(token)
            then = then.decode('base64')
        except KeyError:
            return '/about/me.html', user

        if action not in ACTIONS:
            raise Response(400)

        if action == 'connect' and user.ANON:
            raise Response(404)

        oauth = OAuth1(
            getattr(website, '%s_consumer_key' % self.name),
            getattr(website, '%s_consumer_secret' % self.name),
            token,
            secret,
        )
        response = requests.post(
            "%s/oauth/access_token" % self.api_url,
            data={"oauth_verifier": qs['oauth_verifier']},
            auth=oauth,
        )
        assert response.status_code == 200, response.status_code

        reply = parse_qs(response.text)
        token = reply['oauth_token'][0]
        secret = reply['oauth_token_secret'][0]
        if self.username_key in reply:
            username = reply[self.username_key][0]
        else:
            username = None

        user_info = self.get_user_info(username, token, secret)

        return self.user_action(request, website, user, then, action, user_info)


class PlatformOAuth2(Platform):

    def handle_oauth_callback(self, request, website, user):
        qs = request.line.uri.querystring

        if 'error' in qs or not ('code' in qs and 'data' in qs):
            raise Response(403)

        # Determine what we're supposed to do.
        data = qs['data'].decode('base64').decode('UTF-8')
        action, then = data.split(',', 1)
        if action not in ACTIONS:
            raise Response(400)

        if action == 'connect' and user.ANON:
            raise Response(404)

        # Load user info.
        user_info = self.oauth_dance(website, qs)

        return self.user_action(request, website, user, then, action, user_info)

    def set_oauth_tokens(self, access_token, refresh_token, expires):
        """
        Updates the elsewhere row with the given access token, refresh token, and Python datetime
        """

        self.db.run("""
            UPDATE elsewhere 
            SET (access_token, refresh_token, expires) 
            = (%s, %s, %s) 
            WHERE platform=%s AND user_id=%s
        """, (access_token, refresh_token, expires, self.platform, self.user_id))
