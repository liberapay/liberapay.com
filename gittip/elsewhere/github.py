from __future__ import absolute_import, division, print_function, unicode_literals

import logging
import os

import requests
from aspen import json, Response
from aspen.http.request import UnicodeWithParams
from aspen.utils import typecheck
from aspen.website import Website
from gittip import log
from gittip.elsewhere import ACTIONS, AccountElsewhere, PlatformOAuth2


class GitHubAccount(AccountElsewhere):

    @property
    def display_name(self):
        return self.user_info['login']

    @property
    def img_src(self):
        src = ''

        # GitHub -> Gravatar: http://en.gravatar.com/site/implement/images/
        if 'gravatar_id' in self.user_info:
            gravatar_hash = self.user_info['gravatar_id']
            src = "https://www.gravatar.com/avatar/%s.jpg?s=%s"
            src %= (gravatar_hash, 128)

        return src

    @property
    def html_url(self):
        return self.user_info['html_url']



class GitHub(PlatformOAuth2):

    name = 'github'
    account_elsewhere_subclass = GitHubAccount
    username_key = 'login'
    user_id_key = 'id'


    def oauth_url(self, website, action, then=u""):
        """Given a website object and a string, return a URL string.

        `action' is one of 'opt-in', 'lock' and 'unlock'

        `then' is either a github username or an URL starting with '/'. It's
            where we'll send the user after we get the redirect back from
            GitHub.

        """
        typecheck(website, Website, action, unicode, then, unicode)
        assert action in ACTIONS
        url = u"https://github.com/login/oauth/authorize?client_id=%s&redirect_uri=%s"
        url %= (website.github_client_id, website.github_callback)

        # Pack action,then into data and base64-encode. Querystring isn't
        # available because it's consumed by the initial GitHub request.

        data = u'%s,%s' % (action, then)
        data = data.encode('UTF-8').encode('base64').strip().decode('US-ASCII')
        url += u'?data=%s' % data
        return url


    def oauth_dance(self, website, qs):
        """Given a querystring, return a dict of user_info.

        The querystring should be the querystring that we get from GitHub when
        we send the user to the return value of oauth_url above.

        See also:

            http://developer.github.com/v3/oauth/

        """

        log("Doing an OAuth dance with Github.")

        data = { 'code': qs['code'].encode('US-ASCII')
               , 'client_id': website.github_client_id
               , 'client_secret': website.github_client_secret
                }
        r = requests.post("https://github.com/login/oauth/access_token", data=data)
        assert r.status_code == 200, (r.status_code, r.text)

        back = dict([pair.split('=') for pair in r.text.split('&')]) # XXX
        if 'error' in back:
            raise Response(400, back['error'].encode('utf-8'))
        assert back.get('token_type', '') == 'bearer', back
        access_token = back['access_token']

        r = requests.get( "https://api.github.com/user"
                        , headers={'Authorization': 'token %s' % access_token}
                         )
        assert r.status_code == 200, (r.status_code, r.text)
        user_info = json.loads(r.text)
        log("Done with OAuth dance with Github for %s (%s)."
            % (user_info['login'], user_info['id']))

        return user_info


    def get_user_info(self, login):
        """Get the given user's information from the DB or failing that, github.

        :param login:
            A unicode string representing a username in github.

        :returns:
            A dictionary containing github specific information for the user.
        """
        typecheck(login, (unicode, UnicodeWithParams))

        url = "https://api.github.com/users/%s"
        user_info = requests.get(url % login, params={
            'client_id': os.environ.get('GITHUB_CLIENT_ID'),
            'client_secret': os.environ.get('GITHUB_CLIENT_SECRET')
        })
        status = user_info.status_code
        content = user_info.text

        # Calculate how much of our ratelimit we have consumed
        remaining = int(user_info.headers['x-ratelimit-remaining'])
        limit = int(user_info.headers['x-ratelimit-limit'])
        # thanks to from __future__ import division this is a float
        percent_remaining = remaining/limit

        log_msg = ''
        log_lvl = None
        # We want anything 50% or over
        if 0.5 <= percent_remaining:
            log_msg = ("{0}% of GitHub's ratelimit has been consumed. {1}"
                       " requests remaining.").format(percent_remaining * 100,
                                                      remaining)
        if 0.5 <= percent_remaining < 0.8:
            log_lvl = logging.WARNING
        elif 0.8 <= percent_remaining < 0.95:
            log_lvl = logging.ERROR
        elif 0.95 <= percent_remaining:
            log_lvl = logging.CRITICAL

        if log_msg and log_lvl:
            log(log_msg, log_lvl)

        if status == 200:
            user_info = json.loads(content)
        elif status == 404:
            raise Response(404,
                           "GitHub identity '{0}' not found.".format(login))
        else:
            log("Github api responded with {0}: {1}".format(status, content),
                level=logging.WARNING)
            raise Response(502, "GitHub lookup failed with %d." % status)

        return user_info
