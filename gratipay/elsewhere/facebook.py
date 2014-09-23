from __future__ import absolute_import, division, print_function, unicode_literals

from gratipay.elsewhere import PlatformOAuth2
from gratipay.elsewhere._extractors import key


class Facebook(PlatformOAuth2):

    # Platform attributes
    name = 'facebook'
    display_name = 'Facebook'
    account_url = 'https://www.facebook.com/{user_name}'

    # Auth attributes
    auth_url = 'https://www.facebook.com/dialog/oauth'
    access_token_url = 'https://graph.facebook.com/oauth/access_token'
    oauth_default_scope = ['public_profile,email']

    # API attributes
    api_format = 'json'
    api_url = 'https://graph.facebook.com'
    api_user_info_path = '/{user_name}'
    api_user_self_info_path = '/me'

    # User info extractors
    x_user_id = key('id')
    x_user_name = key('username')
    x_display_name = key('name')
    x_email = key('email')

    def x_avatar_url(self, extracted, info, default):
        return 'https://graph.facebook.com/' + extracted.user_id + '/picture?width=256&height=256'
