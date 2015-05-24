from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.elsewhere import PlatformOAuth2
from liberapay.elsewhere._extractors import any_key, key
from liberapay.elsewhere._paginators import query_param_paginator


class Google(PlatformOAuth2):

    # Platform attributes
    name = 'google'
    display_name = 'Google'
    account_url = 'https://plus.google.com/{user_id}'
    optional_user_name = True

    # Auth attributes
    auth_url = 'https://accounts.google.com/o/oauth2/auth'
    access_token_url = 'https://accounts.google.com/o/oauth2/token'
    oauth_default_scope = ['https://www.googleapis.com/auth/userinfo.email',
                           'https://www.googleapis.com/auth/plus.login']

    # API attributes
    api_format = 'json'
    api_paginator = query_param_paginator('pageToken',
                                          next='nextPageToken',
                                          page='items',
                                          total='totalItems')
    api_url = 'https://www.googleapis.com/plus/v1'
    api_user_info_path = '/people/{user_id}'
    api_user_self_info_path = '/people/me'
    api_friends_path = '/people/{user_id}/people/visible'
    api_friends_limited = True

    # User info extractors
    x_user_id = key('id')
    x_display_name = key('displayName')
    x_email = any_key(('emails', 0), clean=lambda d: d.get('value'))
    x_avatar_url = key('image', clean=lambda d: d.get('url'))

    def x_user_name(self, extracted, info, *default):
        url = info.get('url', '')
        return url[25:] if url.startswith('https://plus.google.com/+') else None
