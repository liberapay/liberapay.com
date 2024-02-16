from liberapay.elsewhere._base import PlatformOAuth2
from liberapay.elsewhere._extractors import any_key, key
from liberapay.elsewhere._paginators import query_param_paginator


class Youtube(PlatformOAuth2):

    # Platform attributes
    based_on = 'google'
    name = 'youtube'
    display_name = 'YouTube'
    account_url = 'https://youtube.com/channel/{user_id}'
    optional_user_name = True
    user_type = 'channel'

    # Auth attributes
    auth_url = 'https://accounts.google.com/o/oauth2/auth?access_type=offline'
    access_token_url = 'https://accounts.google.com/o/oauth2/token'
    oauth_default_scope = ['https://www.googleapis.com/auth/youtube.readonly']

    # API attributes
    api_format = 'json'
    api_paginator = query_param_paginator('pageToken',
                                          next='nextPageToken',
                                          page='items',
                                          total=('pageInfo', 'totalResults'))
    api_url = 'https://www.googleapis.com/youtube/v3'
    api_user_info_path = '/channels?part=snippet&id={user_id}'
    api_user_self_info_path = '/channels?part=snippet&mine=true'
    # api_follows_path = '/subscriptions?part=snippet&mine=true'
    # ↑ https://github.com/liberapay/liberapay.com/issues/1762
    api_search_path = '/search?part=snippet&type=channel&q={query}'

    # User info extractors
    x_user_info = key('items')
    x_user_id = any_key(('snippet', 'resourceId', 'channelId'), 'id')
    x_display_name = any_key(('snippet', 'title'))
    x_avatar_url = any_key(('snippet', 'thumbnails', 'medium', 'url'))
    x_description = any_key(('snippet', 'description'))
