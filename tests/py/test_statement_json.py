from __future__ import print_function, unicode_literals

import json

from gratipay.testing import Harness


class Tests(Harness):

    def change_statement(self, statement, auth_as='alice',
            expecting_error=False):
        self.make_participant('alice', claimed_time='now')

        method = self.client.POST if not expecting_error else self.client.PxST
        response = method( "/alice/statement.json"
                         , {'statement': statement}
                         , auth_as=auth_as
                          )
        return response

    def test_participant_can_change_their_statement(self):
        response = self.change_statement('being awesome.')
        actual = json.loads(response.body)['statement']
        assert actual == '<p>I am making the world better by being awesome.</p>\n'

    def test_anonymous_gets_403(self):
        response = self.change_statement( 'being awesome.'
                                        , auth_as=None
                                        , expecting_error=True
                                         )
        assert response.code == 403, response.code
