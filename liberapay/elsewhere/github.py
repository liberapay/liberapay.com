from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.elsewhere import PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import header_links_paginator


class GitHub(PlatformOAuth2):

    # Platform attributes
    name = 'github'
    display_name = 'GitHub'
    account_url = 'https://github.com/{user_name}'
    allows_team_connect = True

    # Auth attributes
    auth_url = 'https://github.com/login/oauth/authorize'
    access_token_url = 'https://github.com/login/oauth/access_token'
    oauth_email_scope = 'user:email'
    oauth_default_scope = ['read:org']

    # API attributes
    api_format = 'json'
    api_paginator = header_links_paginator()
    api_url = 'https://api.github.com'
    api_user_info_path = '/user/{user_id}'
    api_user_name_info_path = '/users/{user_name}'
    api_user_self_info_path = '/user'
    api_team_members_path = '/orgs/{user_name}/public_members'
    api_friends_path = '/users/{user_name}/following'
    ratelimit_headers_prefix = 'x-ratelimit-'

    # User info extractors
    x_user_id = key('id')
    x_user_name = key('login')
    x_display_name = key('name')
    x_email = key('email')
    x_gravatar_id = key('gravatar_id')
    x_avatar_url = key('avatar_url')
    x_is_team = key('type', clean=lambda t: t.lower() == 'organization')

    def is_team_admin(self, team_name, sess):
        user_teams = self.api_parser(self.api_get('/user/teams', sess=sess))
        return any(team.get('organization', {}).get('login') == team_name and
                   team.get('permission') == 'admin'
                   for team in user_teams)
