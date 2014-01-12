import logging

import gittip
import requests
from aspen import json, log, Response
from aspen.http.request import PathPart
from aspen.utils import typecheck
from gittip.elsewhere import AccountElsewhere



class OpenStreetMapAccount(AccountElsewhere):
    platform = u'openstreetmap'

    def get_url(self):
        return self.user_info['html_url']

    def get_user_name(self):
        return self.user_info['username']

    def get_platform_icon(self):
        return "/assets/icons/openstreetmap.12.png"


def oauth_url(website, action, then=""):
    """Return a URL to start oauth dancing with OpenStreetMap.

    For GitHub we can pass action and then through a querystring. For OpenStreetMap
    we can't, so we send people through a local URL first where we stash this
    info in an in-memory cache (eep! needs refactoring to scale).

    Not sure why website is here. Vestige from GitHub forebear?

    """
    then = then.encode('base64').strip()
    return "/on/openstreetmap/redirect?action=%s&then=%s" % (action, then)


def get_user_info(db, username, osm_api_url):
    """Get the given user's information from the DB or failing that, openstreetmap.

    :param username:
        A unicode string representing a username in OpenStreetMap.

    :param osm_api_url:
	URL of OpenStreetMap API.

    :returns:
        A dictionary containing OpenStreetMap specific information for the user.
    """
    typecheck(username, (unicode, PathPart))
    rec = db.one("""
        SELECT user_info FROM elsewhere
        WHERE platform='openstreetmap'
        AND user_info->'username' = %s
    """, (username,))
    if rec is not None:
        user_info = rec
    else:
        osm_user = requests.get("%s/user/%s" % (osm_api_url, username))
        if osm_user.status_code == 200:
            log("User %s found in OpenStreetMap but not in gittip." % username)
            user_info = None
        elif osm_user.status_code == 404:
            raise Response(404,
                           "OpenStreetMap identity '{0}' not found.".format(username))
        else:
            log("OpenStreetMap api responded with {0}: {1}".format(status, content),
                level=logging.WARNING)
            raise Response(502, "OpenStreetMap lookup failed with %d." % status)

    return user_info
