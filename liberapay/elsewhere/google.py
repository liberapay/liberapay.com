from functools import partial

from liberapay.elsewhere._base import PlatformOAuth2
from liberapay.elsewhere._extractors import any_key, key
from liberapay.elsewhere._paginators import _strip_prefix, query_param_paginator


class Google(PlatformOAuth2):

    # Platform attributes
    name = 'google'
    display_name = 'Google'
    fontawesome_name = name
    account_url = None
    optional_user_name = True

    # Auth attributes
    # https://developers.google.com/identity/protocols/OAuth2WebServer
    auth_url = 'https://accounts.google.com/o/oauth2/auth?access_type=offline&include_granted_scopes=true'
    access_token_url = 'https://accounts.google.com/o/oauth2/token'
    # https://developers.google.com/identity/protocols/googlescopes
    oauth_default_scope = ['https://www.googleapis.com/auth/userinfo.profile']
    oauth_friends_scope = 'https://www.googleapis.com/auth/contacts.readonly'

    # https://developers.google.com/people/api/rest/v1/people/get
    person_fields = 'personFields=names,nicknames,photos,taglines'

    # API attributes
    api_requires_user_token = True
    api_format = 'json'
    api_paginator = query_param_paginator('pageToken',
                                          next='nextPageToken',
                                          total='totalItems')
    api_url = 'https://people.googleapis.com/v1'
    api_user_info_path = '/people/{user_id}?%s' % person_fields
    api_user_self_info_path = '/people/me?%s' % person_fields
    api_friends_path = '/people/me/connections?%s' % person_fields

    # User info extractors
    x_user_id = key('resourceName', clean=partial(_strip_prefix, 'people/'))
    x_display_name = any_key(('names', 'displayName'))
    x_avatar_url = any_key(
        'coverPhotos', 'photos',
        clean=lambda d: None if d.get('default') else d['url']
    )
    x_description = any_key(('taglines', 'value'))

    def x_user_info(self, extracted, info, *default):
        """Reduce a Person object to its primary values.

        Docs: https://developers.google.com/people/api/rest/v1/people#Person
        """
        for k, v in list(info.items()):
            if type(v) is list:
                info[k] = get_primary(v)
        return info


def get_primary(l):
    return next((d for d in l if d['metadata']['primary']), None)
