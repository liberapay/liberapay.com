import json

from liberapay.exceptions import (
    AuthRequired,
    CommunityAlreadyExists,
)
from liberapay.models.community import Community
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Alice joins a community.
        self.alice = self.make_participant('alice')
        c = self.alice.create_community('C++')
        self.alice.upsert_community_membership(True, c.id)

    def test_community_member_shows_up_on_community_listing(self):
        html = self.client.GET('/for/C++/').text
        assert html.count('alice') == 4  # entry in New Members


class TestCommunitiesJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant("alice")
        self.c_id = str(self.alice.create_community('test').id)

    def test_post_bad_id_returns_400(self):
        response = self.client.PxST('/alice/edit/communities',
                                    {'do': 'join:NaN'},
                                    auth_as=self.alice)
        assert response.code == 400

    def test_joining_and_leaving_community(self):
        response = self.client.PxST('/alice/edit/communities',
                                    {'do': 'join:'+self.c_id},
                                    auth_as=self.alice, xhr=True)

        r = json.loads(response.text)
        assert r == {}

        response = self.client.PxST('/alice/edit/communities',
                                    {'do': 'leave:'+self.c_id},
                                    auth_as=self.alice, xhr=True)

        communities = self.alice.get_communities()
        assert len(communities) == 0


class TestCommunityActions(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant("alice")
        self.bob = self.make_participant("bob")
        self.community = Community.create('test', self.alice.id)

    def test_post_bad_name_returns_404(self):
        response = self.client.PxST('/for/Bad:Name!/subscribe',
                                    auth_as=self.alice)
        assert response.code == 404

    def test_subscribe_and_unsubscribe(self):
        # Subscribe
        response = self.client.POST('/for/test/subscribe', auth_as=self.bob, xhr=True)
        assert response.code == 200
        p = self.community.participant.refetch()
        assert p.nsubscribers == 1

        # Subscribe again, shouldn't do anything
        response = self.client.POST('/for/test/subscribe', auth_as=self.bob, xhr=True)
        assert response.code == 200
        p = self.community.participant.refetch()
        assert p.nsubscribers == 1

        # Unsubscribe
        self.client.POST('/for/test/unsubscribe', auth_as=self.bob, xhr=True)
        communities = self.bob.get_communities()
        assert len(communities) == 0

    def test_subscribe_and_unsubscribe_as_anon(self):
        response = self.client.POST('/for/test/subscribe', xhr=True, raise_immediately=False)
        assert response.code == 403

        response = self.client.POST('/for/test/unsubscribe', xhr=True, raise_immediately=False)
        assert response.code == 403

    def test_join_and_leave(self):
        with self.assertRaises(AuthRequired):
            self.client.POST('/for/test/join')

        self.client.POST('/for/test/join', auth_as=self.bob, xhr=True)

        communities = self.bob.get_communities()
        assert len(communities) == 1

        self.client.POST('/for/test/leave', auth_as=self.bob, xhr=True)

        communities = self.bob.get_communities()
        assert len(communities) == 0

    def test_create_community_already_taken(self):
        with self.assertRaises(CommunityAlreadyExists):
            Community.create('test', self.alice.id)

    def test_create_community_already_taken_is_case_insensitive(self):
        with self.assertRaises(CommunityAlreadyExists):
            Community.create('TeSt', self.alice.id)

    def test_unconfusable(self):
        self.assertEqual('user2', Community._unconfusable('user2'))
        self.assertEqual('alice', Community._unconfusable('alice'))
        latin_string = 'AlaskaJazz'
        mixed_string = 'ΑlaskaJazz'
        self.assertNotEqual(latin_string, mixed_string)
        self.assertEqual(latin_string, Community._unconfusable(mixed_string))

    def test_create_community_already_taken_with_confusable_homoglyphs(self):
        latin_string = 'AlaskaJazz'
        mixed_string = 'ΑlaskaJazz'

        Community.create(latin_string, self.bob.id)
        with self.assertRaises(CommunityAlreadyExists):
            Community.create(mixed_string, self.alice.id)


class TestCommunityEdit(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant("alice")
        self.community = Community.create('test', self.alice.id)

    def test_creator_can_edit_community(self):
        data = {'lang': 'en', 'subtitle': '', 'sidebar': ''}
        response = self.client.POST('/for/test/edit', data, auth_as=self.alice)
        assert response.code == 200

    def test_others_cant_edit_community(self):
        response = self.client.PxST('/for/test/edit')
        assert response.code == 403
        bob = self.make_participant('bob')
        response = self.client.PxST('/for/test/edit', auth_as=bob)
        assert response.code == 403

    def test_multilingual_community_edit_form_has_real_lang(self):
        assert self.community.lang == 'mul'
        response = self.client.GET('/for/test/edit', auth_as=self.alice)
        assert response.code == 200
        assert 'name="lang" value="mul"' not in response.text


class TestForCommunityJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        alice = self.make_participant('alice')
        self.community = alice.create_community('test')
        alice.upsert_community_membership(True, self.community.id)
        self.add_participant('bob')
        carl = self.add_participant('carl')
        carl.upsert_community_membership(False, self.community.id)

    def add_participant(self, participant_name):
        participant = self.make_participant(participant_name)
        participant.upsert_community_membership(True, self.community.id)
        return participant

    def test_get_non_existing_community(self):
        response = self.client.GxT('/for/NonExisting/index.json')
        assert response.code == 404

    def test_get_existing_community(self):
        response = self.client.GET('/for/test/index.json')
        result = json.loads(response.text)
        # assert len(result['animators']) == 2  # Not implemented yet
        assert result['name'] == 'test'

    def test_post_not_supported(self):
        response = self.client.PxST('/for/test/index.json')
        assert response.code == 405

    def test_limit(self):
        response = self.client.GET('/for/test/index.json?limit=1')
        json.loads(response.text)
        # assert len(result['animators']) == 1  # Not implemented yet

    def test_offset(self):
        response = self.client.GET('/for/test/index.json?offset=1')
        json.loads(response.text)
        # assert len(result['animators']) == 1  # Not implemented yet

    def test_max_limit(self):
        for i in range(110):
            self.add_participant(str(i))
        response = self.client.GET('/for/test/index.json?limit=200')
        json.loads(response.text)
        # assert len(result['animators']) == 100  # Not implemented yet

    def test_invalid_limit(self):
        response = self.client.GxT('/for/test/index.json?limit=abc')
        assert response.code == 400

    def test_invalid_offset(self):
        response = self.client.GxT('/for/test/index.json?offset=abc')
        assert response.code == 400
