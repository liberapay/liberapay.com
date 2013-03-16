import datetime
import gittip
import requests
from aspen import json, log, Response
from aspen.utils import to_age, utc, typecheck
from aspen.website import Website
from gittip.elsewhere import AccountElsewhere, ACTIONS, _resolve


class GoogleAccount(AccountElsewhere):
    platform = u'google'

    def get_url(self):
        return "https://plus.google.com/" + self.user_info['screen_name']


def resolve(screen_name):
    return _resolve(u'google', u'screen_name', screen_name)


def oauth_url(website, action, then=""):
    """Return a URL to start oauth dancing with Google.

    """
    typecheck(website, Website, action, unicode, then, unicode)
    assert action in ACTIONS

    # Pack action,then into data and base64-encode. Querystring isn't
    # available because it's consumed by the initial GitHub request.

    data = u'%s,%s' % (action, then)
    data = data.encode('UTF-8').encode('base64').decode('US-ASCII')

    url = u'https://accounts.google.com/o/oauth2/auth?response_type=code&client_id=%s&redirect_uri=%s&state=%s'
    url %= (website.google_client_id, website.google_callback, data)

    return url


def get_user_info(screen_name):
    """Given a unicode, return a dict.
    """
    typecheck(screen_name, unicode)
    rec = gittip.db.fetchone( "SELECT user_info FROM elsewhere "
                              "WHERE platform='google' "
                              "AND user_info->'screen_name' = %s"
                            , (screen_name,)
                             )
    if rec is not None:
        user_info = rec['user_info']
    else:
        url = "https://www.googleapis.com/plus/v1/people/%s?key=AIzaSyDFwxAtyIPi08FgI58rMsL5A9CqvL3kOaY"
        user_info = requests.get(url % screen_name)


        # Keep an eye on our API usage.
        # =================================

        # rate_limit = user_info.headers['X-RateLimit-Limit']
        # rate_limit_remaining = user_info.headers['X-RateLimit-Remaining']
        # rate_limit_reset = user_info.headers['X-RateLimit-Reset']

        # try:
        #     rate_limit = int(rate_limit)
        #     rate_limit_remaining = int(rate_limit_remaining)
        #     rate_limit_reset = int(rate_limit_reset)
        # except (TypeError, ValueError):
        #     log( "Got weird rate headers from Twitter: %s %s %s"
        #        % (rate_limit, rate_limit_remaining, rate_limit_reset)
        #         )
        # else:
        #     reset = datetime.datetime.fromtimestamp(rate_limit_reset, tz=utc)
        #     reset = to_age(reset)
        #     log( "Twitter API calls used: %d / %d. Resets %s."
        #        % (rate_limit - rate_limit_remaining, rate_limit, reset)
        #         )


        if user_info.status_code == 200:
            user_info = json.loads(user_info.text)
            user_info['profile_image'] = user_info['image']['url'].split('?')[0]


        else:
            log("Google lookup failed with %d." % user_info.status_code)
            raise Response(404)

    return user_info
