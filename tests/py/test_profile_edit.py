from liberapay.testing import Harness


class Tests(Harness):

    def edit_statement(self, lang, statement, auth_as='alice', action='publish'):
        alice = self.make_participant('alice')
        return self.client.POST(
            "/alice/edit/statement",
            {'lang': lang, 'statement': statement, 'action': action},
            auth_as=alice if auth_as == 'alice' else auth_as,
            raise_immediately=False
        )

    def test_anonymous_gets_403(self):
        r = self.edit_statement('en', 'Some statement', auth_as=None)
        assert r.code == 403

    def test_participant_can_change_their_statement(self):
        r = self.edit_statement('en', 'Lorem ipsum')
        assert r.code == 302
        r = self.client.GET('/alice/')
        assert '<p>Lorem ipsum</p>' in r.text, r.text

    def test_participant_can_preview_their_statement(self):
        r = self.edit_statement('en', 'Lorem ipsum', action='preview')
        assert r.code == 200
        assert '<p>Lorem ipsum</p>' in r.text, r.text

    def test_participant_can_switch_language(self):
        alice = self.make_participant('alice')
        r = self.client.PxST(
            "/alice/edit/statement",
            {'lang': 'en', 'switch_lang': 'fr', 'statement': '', 'action': 'switch'},
            auth_as=alice
        )
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/edit/statement?lang=fr'

    def test_participant_is_warned_of_unsaved_changes_when_switching_language(self):
        alice = self.make_participant('alice')
        r = self.client.POST(
            "/alice/edit/statement",
            {'lang': 'en', 'switch_lang': 'fr', 'statement': 'foo', 'action': 'switch'},
            auth_as=alice
        )
        assert r.code == 200
        assert " are you sure you want to discard them?" in r.text, r.text
        r = self.client.PxST(
            "/alice/edit/statement",
            {'lang': 'en', 'switch_lang': 'fr', 'statement': 'foo', 'action': 'switch', 'discard': 'yes'},
            auth_as=alice
        )
        assert r.code == 302
