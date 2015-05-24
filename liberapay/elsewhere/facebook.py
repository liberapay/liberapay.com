from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.elsewhere import PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import keys_paginator


class Facebook(PlatformOAuth2):

    # Platform attributes
    name = 'facebook'
    display_name = 'Facebook'
    account_url = 'https://www.facebook.com/profile.php?id={user_id}'
    optional_user_name = True

    # Auth attributes
    auth_url = 'https://www.facebook.com/dialog/oauth'
    access_token_url = 'https://graph.facebook.com/oauth/access_token'
    oauth_default_scope = ['public_profile,email,user_friends']

    # API attributes
    api_format = 'json'
    api_paginator = keys_paginator('data', paging='paging', prev='previous')
    api_url = 'https://graph.facebook.com'
    api_user_name_info_path = '/{user_name}'
    api_user_self_info_path = '/me'
    api_friends_path = '/v2.2/{user_id}/friends'
    api_friends_limited = True

    # User info extractors
    x_user_id = key('id')
    x_user_name = key('username')
    x_display_name = key('name')
    x_email = key('email')

    def x_avatar_url(self, extracted, info, default):
        return 'https://graph.facebook.com/' + extracted.user_id + '/picture?width=256&height=256'
