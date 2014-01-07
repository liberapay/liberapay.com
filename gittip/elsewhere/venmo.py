from gittip.elsewhere import AccountElsewhere
from urllib import urlencode
import requests


class VenmoAccount(AccountElsewhere):
    platform = u'venmo'

    def get_url(self):
        return "https://venmo.com/" + self.user_info['username']

def oauth_url(website):
    connect_params = {
        'client_id': website.venmo_client_id,
        'scope': 'make_payments',
        'redirect_uri': website.venmo_callback,
        'response_type': 'code'
    }
    url = u"https://api.venmo.com/v1/oauth/authorize?{}".format(
        urlencode(connect_params)
    )
    return url

def oauth_dance(website, qs):
    data = {
        'code': qs['code'].encode('US-ASCII'),
        'client_id': website.venmo,
        'client_secret': website.venmo_client_secret
    }
    r = requests.post("https://github.com/login/oauth/access_token", data=data)
    assert r.status_code == 200, (r.status_code, r.text)
