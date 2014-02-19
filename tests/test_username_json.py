from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness


class Tests(Harness):

    def change_username(self, new_username, auth_as='alice', expecting_error=False):
        self.make_participant('alice') if auth_as is not None else ''
        method = self.client.POST if not expecting_error else self.client.PxST
        return method("/alice/username.json", {'username': new_username}, auth_as=auth_as)


    def test_participant_can_change_their_username(self):
        response = self.change_username("bob")
        actual = json.loads(response.body)['username']
        assert actual == "bob"

    def test_anonymous_gets_404(self):
        response = self.change_username("bob", auth_as=None, expecting_error=True)
        assert response.code == 404

    def test_empty(self):
        response = self.change_username('      ', expecting_error=True)
        assert response.code == 400
        assert response.body == "You need to provide a username!"

    def test_invalid(self):
        response = self.change_username("§".encode('utf8'), expecting_error=True)
        assert response.code == 400
        assert response.body == "The username '§' contains invalid characters."

    def test_restricted_username(self):
        response = self.change_username("assets", expecting_error=True)
        assert response.code == 400
        assert response.body == "The username 'assets' is restricted."

    def test_unavailable(self):
        self.make_participant("bob")
        response = self.change_username("bob", expecting_error=True)
        assert response.code == 400
        assert response.body == "The username 'bob' is already taken."

    def test_too_long(self):
        self.make_participant("bob")
        username = "I am way too long, and you know it, and the American people know it."
        response = self.change_username(username, expecting_error=True)
        assert response.code == 400
        assert response.body == "The username '%s' is too long." % username
