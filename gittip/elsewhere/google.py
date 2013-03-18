import datetime
import gittip
import hashlib
import requests
from aspen import json, log, Response
from aspen.utils import to_age, utc, typecheck
from aspen.website import Website
from gittip.elsewhere import AccountElsewhere, ACTIONS, _resolve, ServiceElsewhere, AuthorizationFailure


class GoogleProvider(ServiceElsewhere):
    service_name = 'google'
    oauth_cache = {}

    def get_oauth_init_url(self, next='', action=u'opt-in'):
        nonce = hashlib.md5(datetime.datetime.now().isoformat()).hexdigest()

        state = ','.join((self.username, nonce, action))

        self.oauth_cache[self.username] = nonce

        return ''.join([
            "https://accounts.google.com/o/oauth2/auth",
            "?response_type=code",
            "&client_id=%s",
            "&redirect_uri=%s",
            "&state=%s",
            "&scope=https://www.googleapis.com/auth/userinfo.profile",
        ]) % (self.website.google_client_id, next or 'associate', state)

    def handle_oauth_callback(self, qs):
        # pull info out of the querystring
        username, nonce, action = qs['state'].split(',')

        # Make sure the nonces match our cache
        if nonce != self.oauth_cache.get(username): #TODO: Make this a pop
            raise AuthorizationFailed('Nonces do not match.')

        if action == u'opt-in':
            log('opt-in detected')

        return True






    def _get_user_info(self):
        typecheck(self.username, unicode)

        # Check to see if we've already imported these details
        rec = gittip.db.fetchone( "SELECT user_info FROM elsewhere "
                                  "WHERE platform='google' "
                                  "AND user_info->'screen_name' = %s"
                                , (self.username,)
                                 )
        if rec:
            # Use the record we have
            user_info = rec['user_info']
        else:
            # Call the service's API
            url = 'https://www.googleapis.com/plus/v1/people/%s?key=AIzaSyDFwxAtyIPi08FgI58rMsL5A9CqvL3kOaY'
            response = requests.get(url % self.username)

            # Make sure we got back a valid response
            if response.status_code != 200:
                log("Google user lookup failed with %d." % user_info.status_code)
                raise Response(404)


            external_user = json.loads(response.text)
            self._user_info = external_user

            # Get the user's avatar URL on the outside service.
            # Google's includes a ?sz=50 arg, which makes it really small.
            # We strip that out.
            self.avatar = external_user['image']['url'].split('?')[0]
            self.display_name = external_user['displayName']



class GoogleAccount(AccountElsewhere):
    platform = u'google'

    def get_url(self):
        return "https://plus.google.com/" + self.user_info['screen_name']


def resolve(screen_name):
    return _resolve(u'google', u'screen_name', screen_name)





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
