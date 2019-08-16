from liberapay.elsewhere._base import PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import keys_paginator


class Facebook(PlatformOAuth2):

    # Platform attributes
    name = 'facebook'
    display_name = 'Facebook'
    fontawesome_name = 'facebook-square'
    account_url = None
    optional_user_name = True

    # Auth attributes
    auth_url = 'https://www.facebook.com/v2.10/dialog/oauth'
    access_token_url = 'https://graph.facebook.com/v2.10/oauth/access_token'
    refresh_token_url = None
    oauth_default_scope = ['public_profile']
    oauth_email_scope = 'email'
    oauth_friends_scope = 'user_friends'

    # API attributes
    api_format = 'json'
    api_paginator = keys_paginator('data', paging='paging', prev='previous')
    api_url = 'https://graph.facebook.com/v2.10'
    api_user_self_info_path = '/me?fields=id,name,email'
    api_friends_path = '/me/friends'
    api_friends_limited = True

    # User info extractors
    x_user_id = key('id')
    x_display_name = key('name')
    x_email = key('email')
    x_description = key('bio')

    def x_avatar_url(self, extracted, info, default):
        return 'https://graph.facebook.com/' + extracted.user_id + '/picture?width=256&height=256'
