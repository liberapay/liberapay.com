import gittip
import logging
import requests
import os
from aspen import json, log, Response
from aspen.website import Website
from aspen.utils import typecheck
from gittip.elsewhere import ACTIONS, AccountElsewhere, _resolve

BASE_API_URL = "https://api.bitbucket.org/1.0"

class BitBucketAccount(AccountElsewhere):
    platform = u'bitbucket'

    def get_url(self):
        url = "https://bitbucket.org/%s" % self.user_info["username"]
        return url

def get_user_info(login):
    """Get the given user's information from the DB or failing that, bitbucket.

    :param login:
        A unicode string representing a username in bitbucket.

    :returns:
        A dictionary containing bitbucket specific information for the user.
    """
    typecheck(login, unicode)
    rec = gittip.db.fetchone( "SELECT user_info FROM elsewhere "
                              "WHERE platform='bitbucket' "
                              "AND user_info->'login' = %s"
                            , (login,)
                             )
    if rec is not None:
        user_info = rec['user_info']
    else:
        url = "%s/users/%s"
        #user_info = requests.get(url % (BASE_API_URL, login), params={
            #'client_id': os.environ.get('BITBUCKET_CLIENT_ID'),
            #'client_secret': os.environ.get('BITBUCKET_CLIENT_SECRET')
        #})
        user_info = requests.get(url % (BASE_API_URL, login))
        status = user_info.status_code
        content = user_info.content
        if status == 200:
            user_info = json.loads(content)['user']
        elif status == 404:
            raise Response(404,
                           "BitBucket identity '{0}' not found.".format(login))
        else:
            log("BitBucket api responded with {0}: {1}".format(status, content),
                level=logging.WARNING)
            raise Response(502, "BitBucket lookup failed with %d." % status)

    return user_info
