from liberapay.elsewhere._base import APIEndpoint, PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import header_links_paginator


class GitLab(PlatformOAuth2):

    # Platform attributes
    name = 'gitlab'
    display_name = 'GitLab.com'
    account_url = 'https://gitlab.com/{user_name}'
    repo_url = 'https://gitlab.com/{slug}'
    has_teams = True

    # Auth attributes
    # GitLab uses https://github.com/doorkeeper-gem/doorkeeper
    auth_url = 'https://gitlab.com/oauth/authorize'
    access_token_url = 'https://gitlab.com/oauth/token'
    oauth_default_scope = ['read_user']

    # can_auth_with_client_credentials = True
    # https://gitlab.com/gitlab-org/gitlab-ce/issues/13795

    # API attributes
    # http://doc.gitlab.com/ce/api/
    api_format = 'json'
    api_paginator = header_links_paginator(total_header='X-Total')
    api_url = 'https://gitlab.com/api/v4'
    api_user_info_path = '/users/{user_id}'
    api_user_name_info_path = '/users?username={user_name}'
    api_user_self_info_path = '/user'
    api_team_members_path = '/groups/{user_name}/members'
    api_repos_path = APIEndpoint(
        '/users/{user_id}/projects?owned=true&visibility=public&order_by=last_activity_at&per_page=100',
        use_session=False
    )
    api_starred_path = APIEndpoint(
        '/users/{user_id}/projects?starred=true&visibility=public',
        use_session=False
    )

    # User info extractors
    x_user_id = key('id')
    x_user_name = key('username')
    x_display_name = key('name')
    x_email = key('email')
    x_avatar_url = key('avatar_url')
    x_description = key('bio')

    # Repo info extractors
    x_repo_id = key('id')
    x_repo_name = key('name')
    x_repo_slug = key('path_with_namespace')
    x_repo_description = key('description')
    x_repo_last_update = key('last_activity_at')
    x_repo_is_fork = key('forked_from_project', clean=bool)
    x_repo_stars_count = key('star_count')
    x_repo_owner_id = key('owner', clean=lambda d: d['id'])  # not included in responses to unauthenticated requests
