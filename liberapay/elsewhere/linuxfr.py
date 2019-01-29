from liberapay.elsewhere._base import PlatformOAuth2
from liberapay.elsewhere._extractors import key


class LinuxFr(PlatformOAuth2):

    # Platform attributes
    name = 'linuxfr'
    display_name = 'LinuxFr.org'
    account_url = 'https://linuxfr.org/users/{user_name_lower}'

    # Auth attributes
    # LinuxFr uses https://github.com/doorkeeper-gem/doorkeeper
    auth_url = 'https://linuxfr.org/api/oauth/authorize'
    access_token_url = 'https://linuxfr.org/api/oauth/token'

    # API attributes
    # https://linuxfr.org/developpeur
    api_format = 'json'
    api_url = 'https://linuxfr.org/api/v1'
    api_user_self_info_path = '/me'

    # User info extractors
    x_user_name = key('login')
    x_email = key('email')
