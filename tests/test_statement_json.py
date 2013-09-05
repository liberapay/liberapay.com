from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness
from gittip.testing.client import TestClient


class Tests(Harness):

    def change_statement(self, statement, number='singular', user='alice'):
        self.make_participant('alice')

        client = TestClient()
        response = client.get('/')
        csrf_token = response.request.context['csrf_token']

        response = client.post( "/alice/statement.json"
                              , { 'statement': statement
                                , 'number': number
                                , 'csrf_token': csrf_token
                                 }
                              , user=user
                               )
        return response

    def test_participant_can_change_their_statement(self):
        response = self.change_statement('being awesome.')
        actual = json.loads(response.body)['statement']
        assert actual == 'being awesome.', actual

    def test_participant_can_change_their_number(self):
        response = self.change_statement('', 'plural')
        actual = json.loads(response.body)['number']
        assert actual == 'plural', actual

    def test_anonymous_gets_404(self):
        response = self.change_statement('being awesome.', 'singular', user=None)
        assert response.code == 404, response.code

    def test_invalid_is_400(self):
        response = self.change_statement('', 'none')
        assert response.code == 400, response.code
