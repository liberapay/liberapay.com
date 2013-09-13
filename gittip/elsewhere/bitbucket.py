import logging

import gittip
import requests
from aspen import json, log, Response
from aspen.utils import typecheck
from gittip.elsewhere import AccountElsewhere, _resolve


BASE_API_URL = "https://bitbucket.org/api/1.0"


class BitbucketAccount(AccountElsewhere):
    platform = u'bitbucket'

    def get_url(self):
        url = "https://bitbucket.org/%s" % self.user_info["username"]
        return url


def resolve(login):
    return _resolve(u'bitbucket', u'login', login)


def oauth_url(website, action, then=""):
    """Return a URL to start oauth dancing with Bitbucket.

    For GitHub we can pass action and then through a querystring. For Bitbucket
    we can't, so we send people through a local URL first where we stash this
    info in an in-memory cache (eep! needs refactoring to scale).

    Not sure why website is here. Vestige from GitHub forebear?

    """
    then = then.encode('base64').strip()
    return "/on/bitbucket/redirect?action=%s&then=%s" % (action, then)


def get_user_info(username):
    """Get the given user's information from the DB or failing that, bitbucket.

    :param username:
        A unicode string representing a username in bitbucket.

    :returns:
        A dictionary containing bitbucket specific information for the user.
    """
    typecheck(username, unicode)
    rec = gittip.db.one( "SELECT user_info FROM elsewhere "
                         "WHERE platform='bitbucket' "
                         "AND user_info->'username' = %s"
                       , (username,)
                        )
    if rec is not None:
        user_info = rec
    else:
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
