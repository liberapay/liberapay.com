from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness


class Tests(Harness):

    def change_statement(self, statement, number='singular', auth_as='alice',
            expecting_error=False):
        self.make_participant('alice')

        method = self.client.POST if not expecting_error else self.client.PxST
        response = method( "/alice/statement.json"
                         , {'statement': statement, 'number': number}
                         , auth_as=auth_as
                          )
        return response

    def test_participant_can_change_their_statement(self):
        response = self.change_statement('being awesome.')
        actual = json.loads(response.body)['statement']
        assert actual == 'being awesome.'

    def test_participant_can_change_their_number(self):
        response = self.change_statement('', 'plural')
        actual = json.loads(response.body)['number']
        assert actual == 'plural'

    def test_anonymous_gets_404(self):
        response = self.change_statement( 'being awesome.'
                                        , 'singular'
                                        , auth_as=None
                                        , expecting_error=True
                                         )
        assert response.code == 404, response.code

    def test_invalid_is_400(self):
        response = self.change_statement('', 'none', expecting_error=True)
        assert response.code == 400, response.code
