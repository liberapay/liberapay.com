from liberapay.elsewhere._base import CantReadMembership, PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import header_links_paginator


class GitHub(PlatformOAuth2):

    # Platform attributes
    name = 'github'
    display_name = 'GitHub'
    account_url = 'https://github.com/{user_name}'
    repo_url = 'https://github.com/{slug}'
    has_teams = True

    # Auth attributes
    auth_url = 'https://github.com/login/oauth/authorize'
    access_token_url = 'https://github.com/login/oauth/access_token'
    oauth_email_scope = 'user:email'
    can_auth_with_client_credentials = True
    use_basic_auth_for_app_session = True

    # API attributes
    api_format = 'json'
    api_paginator = header_links_paginator()
    api_url = 'https://api.github.com'
    api_user_info_path = '/user/{user_id}'
    api_user_name_info_path = '/users/{user_name}'
    api_user_self_info_path = '/user'
    api_team_members_path = '/orgs/{user_name}/public_members'
    api_follows_path = '/users/{user_name}/following'
    api_repos_path = '/users/{user_name}/repos?type=owner&sort=updated&per_page=100'
    api_starred_path = '/users/{user_name}/starred'
    ratelimit_headers_prefix = 'x-ratelimit-'

    # User info extractors
    x_user_id = key('id')
    x_user_name = key('login')
    x_display_name = key('name')
    x_email = key('email')
    x_gravatar_id = key('gravatar_id')
    x_avatar_url = key('avatar_url')
    x_is_team = key('type', clean=lambda t: t.lower() == 'organization')
    x_description = key('bio')

    # Repo info extractors
    x_repo_id = key('id')
    x_repo_name = key('name')
    x_repo_slug = key('full_name')
    x_repo_description = key('description')
    x_repo_last_update = key('pushed_at')
    x_repo_is_fork = key('fork')
    x_repo_stars_count = key('stargazers_count')
    x_repo_owner_id = key('owner', clean=lambda d: d['id'])

    def get_CantReadMembership_url(self, account):
        return 'https://github.com/orgs/%s/people' % account.user_name

    def is_team_member(self, org_name, sess, account):
        org_name = org_name.lower()

        # Check public membership first
        response = self.api_get(
            '', '/orgs/'+org_name+'/public_members/'+account.user_name,
            sess=sess, error_handler=None
        )
        if response.status_code == 204:
            return True
        elif response.status_code != 404:
            self.api_error_handler(response, True, self.domain)

        # Check private membership
        response = self.api_get(
            '', '/user/memberships/orgs/'+org_name, sess=sess, error_handler=None
        )
        if response.status_code == 403:
            raise CantReadMembership
        elif response.status_code >= 400:
            self.api_error_handler(response, True, self.domain)
        membership = self.api_parser(response)
        if membership['state'] == 'active':
            return True

        # Try the endpoint we were using before
        user_orgs = self.api_parser(self.api_get('', '/user/orgs', sess=sess))
        return any(org.get('login') == org_name for org in user_orgs)
