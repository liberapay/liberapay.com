from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.elsewhere import PlatformOAuth1
from liberapay.elsewhere._extractors import not_available, xpath


class OpenStreetMap(PlatformOAuth1):

    # Platform attributes
    name = 'openstreetmap'
    display_name = 'OpenStreetMap'
    account_url = 'http://www.openstreetmap.org/user/{user_name}'

    # API attributes
    api_format = 'xml'
    api_user_info_path = '/user/{user_id}'
    api_user_self_info_path = '/user/details'

    # User info extractors
    x_user_id = xpath('./user', attr='id')
    x_user_name = xpath('./user', attr='display_name')
    x_display_name = x_user_name
    x_email = not_available
    x_avatar_url = xpath('./user/img', attr='href')
