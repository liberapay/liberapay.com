from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness


class Tests(Harness):

    def change_username(self, new_username, auth_as='alice'):
        self.make_participant('alice') if auth_as is not None else ''
        csrf_token = self.GET('/', want='request.context')['csrf_token']
        return self.POST( "/alice/username.json"
                        , {'username': new_username, 'csrf_token': csrf_token}
                        , auth_as=auth_as
                         )


    def test_participant_can_change_their_username(self):
        response = self.change_username("bob")
        actual = json.loads(response.body)['username']
        assert actual == "bob"

    def test_anonymous_gets_404(self):
        self.short_circuit = False
        response = self.change_username("bob", auth_as=None)
        assert response.code == 404, (response.code, response.body)

    def test_empty(self):
        self.short_circuit = False
        response = self.change_username('      ')
        assert response.code == 400, (response.code, response.body)

    def test_invalid(self):
        self.short_circuit = False
        response = self.change_username("\u2034".encode('utf8'))
        assert response.code == 400, (response.code, response.body)

    def test_restricted_username(self):
        self.short_circuit = False
        response = self.change_username("assets")
        assert response.code == 400, (response.code, response.body)

    def test_unavailable(self):
        self.short_circuit = False
        self.make_participant("bob")
        response = self.change_username("bob")
        assert response.code == 400, (response.code, response.body)

    def test_too_long(self):
        self.short_circuit = False
        self.make_participant("bob")
        response = self.change_username("I am way too long, and you know it, "
                                        "and I know it, and the American "
                                        "people know it.")
        assert response.code == 400, (response.code, response.body)
