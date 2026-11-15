"""Forgejo (and Gitea) support.

Forgejo is self-hostable and has no single canonical instance, so it is a
multi-domain platform like Mastodon: users connect with a `username@domain`
address and per-instance OAuth credentials live in the `oauth_apps` table.

Unlike Mastodon, Forgejo/Gitea cannot register OAuth applications
programmatically, so credentials must be created by hand. To enable a Forgejo
instance, a site administrator must:

1. Create an OAuth2 application on the instance (user or admin settings) with
   the redirect URI `https://<liberapay-host>/on/forgejo:<instance-domain>/associate`.
2. Insert the resulting credentials into the database:
   INSERT INTO oauth_apps (platform, domain, key, secret)
   VALUES ('forgejo', '<instance-domain>', '<client_id>', '<client_secret>');

Connecting to an instance that has no row in `oauth_apps` raises a friendly
error (see `register_app` below) instead of failing with a 500.
"""

from liberapay.elsewhere._base import APIEndpoint, PlatformOAuth2
from liberapay.elsewhere._extractors import key
from liberapay.elsewhere._paginators import header_links_paginator
from liberapay.elsewhere._utils import extract_domain_from_url
from liberapay.exceptions import LazyResponse


class Forgejo(PlatformOAuth2):

    # Platform attributes
    name = 'forgejo'
    display_name = 'Forgejo'
    single_domain = False
    has_teams = False
    account_url = 'https://{domain}/{user_name}'
    repo_url = 'https://{domain}/{slug}'

    def example_account_address(self, _):
        return _('example@codeberg.org')

    # Auth attributes (Forgejo/Gitea OAuth2 provider)
    auth_url = 'https://{domain}/login/oauth/authorize'
    access_token_url = 'https://{domain}/login/oauth/access_token'

    # API attributes
    api_format = 'json'
    api_paginator = header_links_paginator(total_header='X-Total-Count')
    api_url = 'https://{domain}/api/v1'
    api_user_info_path = '/users/{user_name}'
    api_user_self_info_path = '/user'
    # Public repos only (unauthenticated), mirroring GitLab's privacy stance.
    api_repos_path = APIEndpoint('/users/{user_name}/repos?limit=50', use_session=False)

    # User info extractors
    x_domain = key('html_url', clean=extract_domain_from_url)
    x_user_id = key('id')
    x_user_name = key('login')
    x_display_name = key('full_name')
    x_email = key('email')
    x_avatar_url = key('avatar_url')
    x_description = key('description')

    # Repo info extractors
    x_repo_id = key('id')
    x_repo_name = key('name')
    x_repo_slug = key('full_name')
    x_repo_description = key('description')
    x_repo_last_update = key('updated_at')
    x_repo_is_fork = key('fork')
    x_repo_stars_count = key('stars_count')
    x_repo_owner_id = key('owner', clean=lambda d: d['id'])

    def register_app(self, domain):
        msg = lambda _: _(
            "Liberapay doesn't have an OAuth application registered on the "
            "{platform} instance at {domain}.",
            platform=self.display_name, domain=domain,
        )
        raise LazyResponse(502, msg)
