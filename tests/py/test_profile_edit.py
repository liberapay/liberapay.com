from liberapay.testing import Harness


LOREM_IPSUM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor "
    "incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis "
    "nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. "
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore "
    "eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt "
    "in culpa qui officia deserunt mollit anim id est laborum."
)


class Tests(Harness):

    def edit_statement(self, lang, statement, auth_as='alice', action='publish', summary=''):
        alice = self.make_participant('alice')
        return self.client.POST(
            "/alice/edit/statement",
            {'lang': lang, 'statement': statement, 'summary': summary, 'action': action},
            auth_as=alice if auth_as == 'alice' else auth_as,
            raise_immediately=False
        )

    def test_anonymous_gets_403(self):
        r = self.edit_statement('en', LOREM_IPSUM, auth_as=None)
        assert r.code == 403

    def test_participant_can_change_their_statement(self):
        r = self.edit_statement('en', LOREM_IPSUM)
        assert r.code == 302
        r = self.client.GET('/alice/')
        assert LOREM_IPSUM in r.text, r.text

    def test_participant_can_preview_their_statement(self):
        r = self.edit_statement('en', LOREM_IPSUM, action='preview')
        assert r.code == 200
        assert LOREM_IPSUM in r.text, r.text

    def test_participant_can_switch_language(self):
        alice = self.make_participant('alice')
        r = self.client.PxST(
            "/alice/edit/statement",
            {'lang': 'en', 'switch_lang': 'fr', 'statement': '', 'summary': '',
             'action': 'switch'},
            auth_as=alice
        )
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/edit/statement?lang=fr'

    def test_participant_is_warned_of_unsaved_changes_when_switching_language(self):
        alice = self.make_participant('alice')
        r = self.client.POST(
            "/alice/edit/statement",
            {'lang': 'en', 'switch_lang': 'fr', 'statement': 'foo', 'summary': '',
             'action': 'switch'},
            auth_as=alice
        )
        assert r.code == 200
        assert " are you sure you want to discard them?" in r.text, r.text
        r = self.client.PxST(
            "/alice/edit/statement",
            {'lang': 'en', 'switch_lang': 'fr', 'statement': 'foo', 'summary': '',
             'action': 'switch', 'discard': 'yes'},
            auth_as=alice
        )
        assert r.code == 302
