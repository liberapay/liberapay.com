from __future__ import absolute_import, division, print_function, unicode_literals

from aspen import Response
from liberapay.elsewhere import PlatformOAuth1
from liberapay.elsewhere._extractors import any_key, key, not_available
from liberapay.elsewhere._paginators import keys_paginator


class Bitbucket(PlatformOAuth1):

    # Platform attributes
    name = 'bitbucket'
    display_name = 'Bitbucket'
    account_url = 'https://bitbucket.org/{user_name}'

    # Auth attributes
    auth_url = 'https://bitbucket.org/api/1.0'
    authorize_path = '/oauth/authenticate'

    # API attributes
    api_format = 'json'
    api_paginator = keys_paginator('values', prev='previous', total='size')
    api_url = 'https://bitbucket.org/api'
    api_user_info_path = '/2.0/users/{user_id}'
    api_user_name_info_path = '/2.0/users/{user_name}'
    api_user_self_info_path = '/2.0/user'
    api_team_members_path = '/2.0/teams/{user_name}/members'
    api_friends_path = '/2.0/users/{user_name}/following'

    # User info extractors
    x_user_info = key('user')
    x_user_id = key('uuid')
    x_user_name = key('username')
    x_display_name = key('display_name')
    x_email = not_available
    x_avatar_url = any_key('avatar', ('links', 'avatar', 'href'))
    x_is_team = key('type', lambda v: v == 'team')

    def api_get(self, path, sess=None, **kw):
        """Extend to manually retry /users/pypy as /teams/pypy.

        Bitbucket gives us a 404 where a 30x would be more helpful.

        """
        try:
            return PlatformOAuth1.api_get(self, path, sess, **kw)
        except Response as response:
            if response.code == 404 and ' is a team account' in response.body:
                assert path.startswith('/2.0/users/')
                path = '/2.0/teams/' + path[11:]
                return PlatformOAuth1.api_get(self, path, sess, **kw)
            else:
                raise
