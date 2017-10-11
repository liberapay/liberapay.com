from __future__ import absolute_import, division, print_function, unicode_literals

from requests_oauthlib import OAuth2Session

from liberapay.elsewhere._base import PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import query_param_paginator


class SpecialDict(dict):

    __nonzero__ = __bool__ = lambda self: True

    def __setitem__(self, k, v):
        if k.lower() == 'authorization' and v and v.startswith('Bearer '):
            v = 'OAuth' + v[6:]
        return dict.__setitem__(self, k, v)


class TwitchOAuthSession(OAuth2Session):
    """
    Twitch's OAuth implementation isn't standard-compliant, it expects `OAuth`
    as the request authorization type instead of `Bearer`.
    """

    def request(self, *args, **kw):
        kw['headers'] = SpecialDict(kw['headers'])
        return super(TwitchOAuthSession, self).request(*args, **kw)


class Twitch(PlatformOAuth2):

    # Platform attributes
    name = 'twitch'
    display_name = 'Twitch'
    account_url = 'https://twitch.tv/{user_name}'
    user_type = 'channel'

    # Auth attributes
    auth_url = 'https://api.twitch.tv/kraken/oauth2/authorize'
    access_token_url = 'https://api.twitch.tv/kraken/oauth2/token'
    oauth_default_scope = ['channel_read']
    session_class = TwitchOAuthSession

    # API attributes
    api_headers = {'Accept': 'application/vnd.twitchtv.v5+json'}
    api_format = 'json'
    api_paginator = query_param_paginator('cursor', next='_cursor', total='_total')
    api_url = 'https://api.twitch.tv/kraken'
    api_user_info_path = '/channels/{user_id}'
    api_user_self_info_path = '/channel'
    api_friends_path = '/users/{user_id}/follows/channels'
    api_search_path = '/search/channels?query={query}'

    # User info extractors
    x_user_info = key('channel')
    x_user_id = key('_id')
    x_user_name = key('name')
    x_display_name = key('display_name')
    x_email = key('email')
    x_avatar_url = key('logo')
    x_description = key('description')
