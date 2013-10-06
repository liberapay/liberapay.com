from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import requests
from aspen import json, log, Response
from aspen.http.request import UnicodeWithParams
from aspen.utils import typecheck
from gittip.elsewhere import AccountElsewhere, Platform


BASE_API_URL = "https://bitbucket.org/api/1.0"


class BitbucketAccount(AccountElsewhere):

    @property
    def display_name(self):
        return self.user_info['username']

    @property
    def img_src(self):
        src = ''
        # XXX Um ... ?
        return src

    @property
    def html_url(self):
        return "https://bitbucket.org/{username}".format(**self.user_info)


class Bitbucket(Platform):

    name = 'bitbucket'
    account_elsewhere_subclass = BitbucketAccount
    username_key = 'username'
    user_id_key = 'username'  # No immutable id. :-/


    def oauth_url(self, action, then=""):
        """Return a URL to start oauth dancing with Bitbucket.

        For GitHub we can pass action and then through a querystring. For Bitbucket
        we can't, so we send people through a local URL first where we stash this
        info in an in-memory cache (eep! needs refactoring to scale).

        Not sure why website is here. Vestige from GitHub forebear?

        """
        then = then.encode('base64').strip()
        return "/on/bitbucket/redirect?action=%s&then=%s" % (action, then)


    def get_user_info(self, username):
        """Get the given user's information from the DB or failing that, bitbucket.

        :param username:
            A unicode string representing a username in bitbucket.

        :returns:
            A dictionary containing bitbucket specific information for the user.
        """
        typecheck(username, (unicode, UnicodeWithParams))
        url = "%s/users/%s?pagelen=100"
        user_info = requests.get(url % (BASE_API_URL, username))
        status = user_info.status_code
        content = user_info.content
        if status == 200:
            user_info = json.loads(content)['user']
        elif status == 404:
            raise Response(404,
                           "Bitbucket identity '{0}' not found.".format(username))
        else:
            log("Bitbucket api responded with {0}: {1}".format(status, content),
                level=logging.WARNING)
            raise Response(502, "Bitbucket lookup failed with %d." % status)

        return user_info
