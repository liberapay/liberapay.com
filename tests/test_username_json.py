from __future__ import print_function, unicode_literals

import json

from gittip.testing import Harness


class Tests(Harness):

    def change_username(self, new_username, auth_as='alice', weird=False):
        if auth_as:
            self.make_participant(auth_as)

        if weird:
            post, args = self.client.PxST, {}
        else:
            post, args = self.client.POST, {'raise_immediately': False}

        r = post('/alice/username.json', {'username': new_username},
                                         auth_as=auth_as, **args)
        return r.code, r.body if weird else json.loads(r.body)

    def test_participant_can_change_their_username(self):
        code, body = self.change_username("bob")
        assert code == 200
        assert body['username'] == "bob"

    def test_anonymous_gets_404(self):
        code, body = self.change_username("bob", auth_as=None, weird=True)
        assert code == 404

    def test_empty(self):
        code, body = self.change_username('      ')
        assert code == 400
        assert body['error_message_long'] == "You need to provide a username!"

    def test_invalid(self):
        code, body = self.change_username("§".encode('utf8'))
        assert code == 400
        assert body['error_message_long'] == "The username '§' contains invalid characters."

    def test_restricted_username(self):
        code, body = self.change_username("assets")
        assert code == 400
        assert body['error_message_long'] == "The username 'assets' is restricted."

    def test_unavailable(self):
        self.make_participant("bob")
        code, body = self.change_username("bob")
        assert code == 400
        assert body['error_message_long'] == "The username 'bob' is already taken."

    def test_too_long(self):
        username = "I am way too long, and you know it, and the American people know it."
        code, body = self.change_username(username)
        assert code == 400
        assert body['error_message_long'] == "The username '%s' is too long." % username
