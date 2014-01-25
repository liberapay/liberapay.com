from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness


class Tests(Harness):
    def change_bitcoin_address(self, address, user='alice', should_fail=True):
        self.make_participant('alice')
        if should_fail:
            response = self.client.PxST("/alice/bitcoin.json",
                               {'bitcoin_address': address,},
                                auth_as=user
            )
        else:
            response = self.client.POST("/alice/bitcoin.json",
                               {'bitcoin_address': address,},
                                auth_as=user
            )
        return response

    def test_participant_can_change_their_address(self):
        response = self.change_bitcoin_address(
            '17NdbrSGoUotzeGCcMMCqnFkEvLymoou9j', should_fail=False)
        actual = json.loads(response.body)['bitcoin_address']
        assert actual == '17NdbrSGoUotzeGCcMMCqnFkEvLymoou9j', actual

    def test_anonymous_gets_404(self):
        response = self.change_bitcoin_address(
            '17NdbrSGoUotzeGCcMMCqnFkEvLymoou9j', user=None)
        assert response.code == 404, response.code

    def test_invalid_is_400(self):
        response = self.change_bitcoin_address('12345')
        assert response.code == 400, response.code
