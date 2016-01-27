from __future__ import absolute_import, division, print_function, unicode_literals

from binascii import hexlify
import hashlib
import os
from time import time
try:
    from urllib.parse import parse_qs, urlencode, urlparse
except ImportError:
    from urllib import urlencode
    from urlparse import parse_qs, urlparse

import requests

from aspen import Response
from liberapay.elsewhere import Platform
from liberapay.elsewhere._extractors import key, not_available


class Bountysource(Platform):

    # Platform attributes
    name = 'bountysource'
    display_name = 'Bountysource'
    account_url = '{platform_data.auth_url}/people/{user_id}'
    optional_user_name = True

    # API attributes
    api_format = 'json'
    api_user_info_path = '/users/{user_id}'
    api_user_self_info_path = '/user'

    # User info extractors
    x_user_id = key('id')
    x_user_name = not_available
    x_display_name = key('display_name')
    x_email = key('email')
    x_avatar_url = key('image_url')

    def get_auth_session(self, token=None):
        sess = requests.Session()
        sess.auth = BountysourceAuth(token)
        return sess

    def get_auth_url(self, user):
        query_id = hexlify(os.urandom(10))
        time_now = int(time())
        raw = '%s.%s.%s' % (user.id, time_now, self.api_secret)
        h = hashlib.md5(raw).hexdigest()
        token = '%s.%s.%s' % (user.id, time_now, h)
        params = dict(
            redirect_url=self.callback_url+'?query_id='+query_id,
            external_access_token=token
        )
        url = self.auth_url+'/auth/liberapay/confirm?'+urlencode(params)
        return url, query_id, ''

    def get_query_id(self, querystring):
        token = querystring['access_token']
        i = token.rfind('.')
        data, data_hash = token[:i], token[i+1:]
        if data_hash != hashlib.md5(data+'.'+self.api_secret).hexdigest():
            raise Response(400, 'Invalid hash in access_token')
        return querystring['query_id']

    def get_user_self_info(self, sess):
        querystring = urlparse(sess._callback_url).query
        info = {k: v[0] if len(v) == 1 else v
                for k, v in parse_qs(querystring).items()}
        info.pop('access_token')
        info.pop('query_id')
        return self.extract_user_info(info)

    def handle_auth_callback(self, url, query_id, unused_arg):
        sess = self.get_auth_session(token=query_id)
        sess._callback_url=url
        return sess


class BountysourceAuth(object):

    def __init__(self, token=None):
        self.token = token

    def __call__(self, req):
        if self.token:
            req.params['access_token'] = self.token
