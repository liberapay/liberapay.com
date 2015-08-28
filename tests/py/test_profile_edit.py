from __future__ import print_function, unicode_literals

from liberapay.testing import Harness


class Tests(Harness):

    def change_statement(self, lang, statement, auth_as='alice'):
        alice = self.make_participant('alice')
        return self.client.PxST(
            "/alice/edit",
            {'lang': lang, 'statement': statement, 'save': 'true'},
            auth_as=alice if auth_as == 'alice' else auth_as
        )

    def test_participant_can_change_their_statement(self):
        r = self.change_statement('en', 'Lorem ipsum')
        assert r.code == 302
        r = self.client.GET('/alice/')
        assert '<p>Lorem ipsum</p>\n' in r.text, r.text

    def test_anonymous_gets_403(self):
        r = self.change_statement('en', 'Some statement', auth_as=None)
        assert r.code == 403
