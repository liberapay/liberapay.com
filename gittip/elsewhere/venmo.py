from gittip.elsewhere import AccountElsewhere
from urllib import urlencode


class VenmoAccount(AccountElsewhere):
    platform = u'venmo'

    def get_url(self):
        return "https://venmo.com/" + self.user_info['username']

def oauth_url(website):
    connect_params = {
        'client_id': website.venmo_client_id,
        'scope': 'make_payments',
        'redirect_uri': website.venmo_callback
    }
    url = u"https://api.venmo.com/v1/oauth/authorize?{}".format(
        urlencode(connect_params)
    )
    return url
