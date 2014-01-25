from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
from os import environ

from aspen import json, log, Response
from aspen.utils import to_age, utc
from gittip.elsewhere import PlatformOAuth1
from gittip.models.account_elsewhere import AccountElsewhere
import requests
from requests_oauthlib import OAuth1


class TwitterAccount(AccountElsewhere):

    @property
    def html_url(self):
        return "https://twitter.com/" + self.user_info['screen_name']

    @property
    def display_name(self):
        return self.user_info['screen_name']

    def get_platform_icon(self):
        return "/assets/icons/twitter.12.png"

    @property
    def img_src(self):
        src = ''

        # https://dev.twitter.com/docs/api/1.1/get/users/show
        if 'profile_image_url_https' in self.user_info:
            src = self.user_info['profile_image_url_https']

            # For Twitter, we don't have good control over size. The
            # biggest option is 73px(?!), but that's too small. Let's go
            # with the original: even though it may be huge, that's
            # preferrable to guaranteed blurriness. :-/

            src = src.replace('_normal.', '.')

        return src


class Twitter(PlatformOAuth1):

    name = 'twitter'
    account_elsewhere_subclass = TwitterAccount
    user_id_key= 'id'
    username_key = 'screen_name'
    api_url = environ['TWITTER_API_URL']


    def oauth_url(self, action, then=""):
        """Return a URL to start oauth dancing with Twitter.

        For GitHub we can pass action and then through a querystring. For Twitter
        we can't, so we send people through a local URL first where we stash this
        info in an in-memory cache (eep! needs refactoring to scale).
        """
        then = then.encode('base64').strip()
        return "/on/twitter/redirect?action=%s&then=%s" % (action, then)


    def get_user_info(self, screen_name, token=None, secret=None):
        """
        """
        if token is None or secret is None:
            token = environ['TWITTER_ACCESS_TOKEN']
            secret = environ['TWITTER_ACCESS_TOKEN_SECRET']
        # Updated using Twython as a point of reference:
        # https://github.com/ryanmcgrath/twython/blob/master/twython/twython.py#L76
        oauth = OAuth1(
            # we do not have access to the website obj,
            # so let's grab the details from the env
            environ['TWITTER_CONSUMER_KEY'],
            environ['TWITTER_CONSUMER_SECRET'],
            token,
            secret,
        )

        url = "https://api.twitter.com/1.1/users/show.json?screen_name=%s"
        user_info = requests.get(url % screen_name, auth=oauth)


        # Keep an eye on our Twitter usage.
        # =================================

        rate_limit = user_info.headers['X-Rate-Limit-Limit']
        rate_limit_remaining = user_info.headers['X-Rate-Limit-Remaining']
        rate_limit_reset = user_info.headers['X-Rate-Limit-Reset']

        try:
            rate_limit = int(rate_limit)
            rate_limit_remaining = int(rate_limit_remaining)
            rate_limit_reset = int(rate_limit_reset)
        except (TypeError, ValueError):
            log( "Got weird rate headers from Twitter: %s %s %s"
               % (rate_limit, rate_limit_remaining, rate_limit_reset)
                )
        else:
            reset = datetime.datetime.fromtimestamp(rate_limit_reset, tz=utc)
            reset = to_age(reset)
            log( "Twitter API calls used: %d / %d. Resets %s."
               % (rate_limit - rate_limit_remaining, rate_limit, reset)
                )


        if user_info.status_code == 200:
            user_info = json.loads(user_info.text)
        else:
            log("Twitter lookup failed with %d." % user_info.status_code)
            raise Response(404)

        # Add user page url.
        user_info['html_url'] = "https://twitter.com/" + screen_name

        return user_info
