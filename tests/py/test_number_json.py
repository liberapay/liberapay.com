from __future__ import print_function, unicode_literals

import json

from gratipay.testing import Harness


class Tests(Harness):

    def change_number(self, number, auth_as='alice', expecting_error=False):
        self.make_participant('alice', claimed_time='now')

        method = self.client.POST if not expecting_error else self.client.PxST
        response = method( "/alice/number.json"
                         , {'number': number}
                         , auth_as=auth_as
                          )
        return response

    def test_participant_can_change_their_number(self):
        response = self.change_number('plural')
        actual = json.loads(response.body)['number']
        assert actual == 'plural'

    def test_invalid_is_400(self):
        response = self.change_number('none', expecting_error=True)
        assert response.code == 400, response.code
