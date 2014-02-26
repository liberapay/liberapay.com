from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.elsewhere import PlatformOAuth2
from gittip.elsewhere._extractors import key


class Venmo(PlatformOAuth2):

    # Platform attributes
    name = 'venmo'
    display_name = 'Venmo'
    account_url = 'https://venmo.com/{user_name}'
    icon = '/assets/icons/venmo.16.png'

    # PlatformOAuth2 attributes
    auth_url = 'https://api.venmo.com/v1/oauth'
    oauth_email_scope = 'access_email'
    oauth_payment_scope = 'make_payments'
    oauth_default_scope = ['access_profile']

    # API attributes
    api_format = 'json'
    api_url = 'https://api.venmo.com/v1'
    api_user_info_path = '/users/{user_id}'
    api_user_self_info_path = '/me'

    # User info extractors
    x_user_info = key('data', clean=lambda d: d.pop('user', d))
    x_user_id = key('id')
    x_user_name = key('username')
    x_display_name = key('display_name')
    x_email = key('email')
    x_avatar_url = key('profile_picture_url')
