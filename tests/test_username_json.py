from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness
from gittip.testing.client import TestClient


class Tests(Harness):

    def change_username(self, new_username, user='alice'):
        self.make_participant('alice')

        client = TestClient()
        response = client.get('/')
        csrf_token = response.request.context['csrf_token']

        response = client.post( "/alice/username.json"
                              , { 'username': new_username
                                , 'csrf_token': csrf_token
                                 }
                              , user=user
                               )
        return response


    def test_participant_can_change_their_username(self):
        response = self.change_username("bob")
        actual = json.loads(response.body)['username']
        assert actual == "bob", actual

    def test_anonymous_gets_404(self):
        response = self.change_username("bob", user=None)
        assert response.code == 404, (response.code, response.body)

    def test_invalid_is_400(self):
        response = self.change_username("\u2034".encode('utf8'))
        assert response.code == 400, (response.code, response.body)

    def test_restricted_username_is_400(self):
        response = self.change_username("assets")
        assert response.code == 400, (response.code, response.body)

    def test_unavailable_is_409(self):
        self.make_participant("bob")
        response = self.change_username("bob")
        assert response.code == 409, (response.code, response.body)

    def test_too_long_is_413(self):
        self.make_participant("bob")
        response = self.change_username("I am way too long, and you know it, "
                                        "and I know it, and the American "
                                        "people know it.")
        assert response.code == 413, (response.code, response.body)
