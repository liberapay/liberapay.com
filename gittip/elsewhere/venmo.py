from gittip.elsewhere import AccountElsewhere
from urllib import urlencode
from aspen import json, Response
import requests


class VenmoAccount(AccountElsewhere):
    platform = u'venmo'

    def get_url(self):
        return "https://venmo.com/" + self.user_info['username']

    def get_profile_image(self):
        return self.user_info['profile_picture_url']

    def get_user_name(self):
        return self.user_info['username']

    def get_display_name(self):
        return self.user_info['display_name']

    def get_platform_icon(self):
        return "/assets/icons/venmo.16.png"

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
    """Return a dictionary of the Venmo response.

    There's an example at: https://developer.venmo.com/docs/authentication
    """

    data = {
        'code': qs['code'].encode('US-ASCII'),
        'client_id': website.venmo_client_id,
        'client_secret': website.venmo_client_secret
    }
    r = requests.post('https://api.venmo.com/v1/oauth/access_token', data=data)
    res_dict = r.json()

    if 'error' in res_dict:
        raise Response(400, res_dict['error']['message'].encode('utf-8'))

    assert r.status_code == 200, (r.status_code, r.text)

    return res_dict
