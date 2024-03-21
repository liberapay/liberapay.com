from liberapay.elsewhere._base import PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import cursor_paginator


class Twitch(PlatformOAuth2):

    # Platform attributes
    name = 'twitch'
    display_name = 'Twitch'
    account_url = 'https://twitch.tv/{user_name}'
    user_type = 'channel'

    # Auth attributes
    # https://dev.twitch.tv/docs/authentication/
    auth_url = 'https://id.twitch.tv/oauth2/authorize'
    access_token_url = 'https://id.twitch.tv/oauth2/token'
    can_auth_with_client_credentials = True

    # API attributes
    api_format = 'json'
    api_paginator = cursor_paginator(
        ('pagination', 'cursor'), page='data', next='after', prev='before'
    )
    api_url = 'https://api.twitch.tv/helix'
    api_user_info_path = '/users?id={user_id}'
    api_user_name_info_path = '/users?login={user_name}'
    api_user_self_info_path = '/users'

    # api_follows_path = '/users/follows?from_id={user_id}'
    # This endpoint only returns user IDs, not a list of user info objects

    # User info extractors
    x_user_info = key('data')
    x_user_id = key('id')
    x_user_name = key('login')
    x_display_name = key('display_name')
    x_email = key('email')
    x_avatar_url = key('profile_image_url')
    x_description = key('description')

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.api_headers = {'Client-ID': self.api_key}
