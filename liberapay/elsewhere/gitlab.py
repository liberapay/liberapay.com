from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.elsewhere._base import PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import header_links_paginator


class GitLab(PlatformOAuth2):

    # Platform attributes
    name = 'gitlab'
    display_name = 'GitLab'
    account_url = 'https://gitlab.com/u/{user_name}'

    # Auth attributes
    # GitLab uses https://github.com/doorkeeper-gem/doorkeeper
    auth_url = 'https://gitlab.com/oauth/authorize'
    access_token_url = 'https://gitlab.com/oauth/token'
    can_auth_with_client_credentials = True

    # API attributes
    # http://doc.gitlab.com/ce/api/
    api_format = 'json'
    api_paginator = header_links_paginator()
    api_url = 'https://gitlab.com/api/v3'
    # api_user_info_path = '/users/{user_id}'
    # api_user_name_info_path = '/users?username={user_name}'
    api_user_self_info_path = '/user'
    # api_team_members_path = '/groups/{user_name}/members'

    # The commented out paths are because we need this:
    # https://gitlab.com/gitlab-org/gitlab-ce/issues/13795

    # User info extractors
    x_user_id = key('id')
    x_user_name = key('username')
    x_display_name = key('name')
    x_email = key('email')
    x_avatar_url = key('avatar_url')
