from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.elsewhere import PlatformOAuth1
from gittip.elsewhere._extractors import key, not_available
from gittip.elsewhere._paginators import keys_paginator


class Bitbucket(PlatformOAuth1):

    # Platform attributes
    name = 'bitbucket'
    display_name = 'Bitbucket'
    account_url = 'https://bitbucket.org/{user_name}'
    icon = '/assets/icons/bitbucket.12.png'

    # Auth attributes
    auth_url = 'https://bitbucket.org/api/1.0'
    authorize_path = '/oauth/authenticate'

    # API attributes
    api_format = 'json'
    api_paginator = keys_paginator(prev='previous')
    api_url = 'https://bitbucket.org/api'
    api_user_info_path = '/1.0/users/{user_name}'
    api_user_self_info_path = '/1.0/user'
    api_team_members_path = '/2.0/teams/{user_name}/members'

    # User info extractors
    x_user_info = key('user')
    x_user_id = not_available  # No immutable id. :-/
    x_user_name = key('username')
    x_display_name = key('display_name')
    x_email = not_available
    x_avatar_url = key('avatar')
    x_is_team = key('is_team')
