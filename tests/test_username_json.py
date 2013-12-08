from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness


class Tests(Harness):

    def change_username(self, new_username, auth_as='alice', raise_immediately=True):
        self.make_participant('alice') if auth_as is not None else ''
        csrf_token = self.client.GET('/', want='request.context')['csrf_token']
        return self.client.POST( "/alice/username.json"
                               , {'username': new_username, 'csrf_token': csrf_token}
                               , auth_as=auth_as
                               , raise_immediately=raise_immediately
                                )


    def test_participant_can_change_their_username(self):
        response = self.change_username("bob")
        actual = json.loads(response.body)['username']
        assert actual == "bob"

    def test_anonymous_gets_404(self):
        response = self.change_username("bob", auth_as=None, raise_immediately=False)
        assert response.code == 404

    def test_empty(self):
        response = self.change_username('      ', raise_immediately=False)
        assert response.code == 400

    def test_invalid(self):
        response = self.change_username("\u2034".encode('utf8'), raise_immediately=False)
        assert response.code == 400

    def test_restricted_username(self):
        response = self.change_username("assets", raise_immediately=False)
        assert response.code == 400

    def test_unavailable(self):
        self.make_participant("bob")
        response = self.change_username("bob", raise_immediately=False)
        assert response.code == 400

    def test_too_long(self):
        self.make_participant("bob")
        response = self.change_username("I am way too long, and you know it, "
                                        "and I know it, and the American "
                                        "people know it.", raise_immediately=False)
        assert response.code == 400
