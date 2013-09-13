from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness
from gittip.testing.client import TestClient


class Tests(Harness):

    def change_bitcoin_address(self, address, user='alice'):
        self.make_participant('alice')

        client = TestClient()
        response = client.get('/')
        csrf_token = response.request.context['csrf_token']

        response = client.post( "/alice/bitcoin.json"
                              , { 'bitcoin_address': address
                                , 'csrf_token': csrf_token
                                 }
                              , user=user
                               )
        return response

    def test_participant_can_change_their_address(self):
        response = self.change_bitcoin_address('17NdbrSGoUotzeGCcMMCqnFkEvLymoou9j')
        actual = json.loads(response.body)['bitcoin_address']
        assert actual == '17NdbrSGoUotzeGCcMMCqnFkEvLymoou9j', actual

    def test_anonymous_gets_404(self):
        response = self.change_bitcoin_address('17NdbrSGoUotzeGCcMMCqnFkEvLymoou9j', user=None)
        assert response.code == 404, response.code

    def test_invalid_is_400(self):
        response = self.change_bitcoin_address('12345')
        assert response.code == 400, response.code
