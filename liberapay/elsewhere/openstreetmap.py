from liberapay.elsewhere._base import PlatformOAuth2
from liberapay.elsewhere._extractors import not_available, xpath


class OpenStreetMap(PlatformOAuth2):

    # Platform attributes
    name = 'openstreetmap'
    display_name = 'OpenStreetMap'
    account_url = 'http://www.openstreetmap.org/user/{user_name}'

    # Auth attributes - https://wiki.openstreetmap.org/wiki/OAuth
    oauth_default_scope = ['read_prefs']

    # API attributes - https://wiki.openstreetmap.org/wiki/API_v0.6
    api_format = 'xml'
    api_user_info_path = '/user/{user_id}'
    api_user_self_info_path = '/user/details'

    # User info extractors
    x_user_id = xpath('./user', attr='id')
    x_user_name = xpath('./user', attr='display_name')
    x_display_name = x_user_name
    x_email = not_available
    x_avatar_url = xpath('./user/img', attr='href')
    x_description = xpath('./user/description')
