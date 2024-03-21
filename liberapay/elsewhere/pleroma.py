from liberapay.elsewhere.mastodon import Mastodon


class Pleroma(Mastodon):
    # https://pleroma.social/

    # Platform attributes
    name = 'pleroma'
    display_name = 'Pleroma'
    account_url = 'https://{domain}/{user_name}'
    single_domain = False

    def example_account_address(self, _):
        return _('example@pleroma.site')
