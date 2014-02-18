from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.elsewhere import PlatformOAuth2
from gittip.elsewhere._extractors import key


class GitHub(PlatformOAuth2):

    # Platform attributes
    name = 'github'
    display_name = 'GitHub'
    account_url = 'https://github.com/{user_name}'
    icon = '/assets/icons/github.12.png'

    # Auth attributes
    auth_url = 'https://github.com/login/oauth'
    oauth_email_scope = 'user:email'

    # API attributes
    api_format = 'json'
    api_url = 'https://api.github.com'
    api_user_info_path = '/users/{user_name}'
    api_user_self_info_path = '/user'
    ratelimit_headers_prefix = 'x-ratelimit-'
    x_user_id = key('id')
    x_user_name = key('login')
    x_display_name = key('name')
    x_email = key('email')
    x_gravatar_id = key('gravatar_id')
    x_avatar_url = key('avatar_url')
    x_is_team = key('type', clean=lambda t: t.lower() == 'organization')
