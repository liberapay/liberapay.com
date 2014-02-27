from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.elsewhere import PlatformOAuth1
from gittip.elsewhere._extractors import key, not_available


class Twitter(PlatformOAuth1):

    # Platform attributes
    name = 'twitter'
    display_name = 'Twitter'
    account_url = 'https://twitter.com/{user_name}'
    icon = '/assets/icons/twitter.12.png'

    # Auth attributes
    auth_url = 'https://api.twitter.com'

    # API attributes
    api_format = 'json'
    api_url = 'https://api.twitter.com/1.1'
    api_user_info_path = '/users/show.json?screen_name={user_name}'
    api_user_self_info_path = '/account/verify_credentials.json'
    ratelimit_headers_prefix = 'x-rate-limit-'

    # User info extractors
    x_user_id = key('id')
    x_user_name = key('screen_name')
    x_display_name = key('name')
    x_email = not_available
    x_avatar_url = key('profile_image_url_https',
                       clean=lambda v: v.replace('_normal.', '.'))
