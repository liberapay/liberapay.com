import json

from liberapay.exceptions import AuthRequired
from liberapay.models.community import Community
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Alice joins a community.
        self.alice = self.make_participant('alice')
        self.com = self.alice.create_community('C++')
        self.alice.upsert_community_membership(True, self.com.id)

    def test_community_member_shows_up_on_community_listing(self):
        html = self.client.GET('/for/C++/').text
        assert html.count('alice') == 4  # entry in New Members

    def test_spam_community_is_hidden(self):
        admin = self.make_participant('admin', privileges=1)
        self.com.participant.upsert_statement('en', "spammy subtitle", 'subtitle')
        self.com.participant.upsert_statement('en', "spammy sidebar", 'sidebar')
        r = self.client.PxST(
            '/admin/users', data={'p_id': str(self.com.participant.id), 'mark_as': 'spam'},
            auth_as=admin,
        )
        assert r.code == 200
        assert json.loads(r.text) == {"msg": "Done, 1 attribute has been updated."}
        r = self.client.GET('/for/C++/', raise_immediately=False)
        assert r.text.count('alice') == 0
        assert r.code == 200
        assert 'spammy' not in r.text
        assert "This profile is marked as spam or fraud." in r.text
        r = self.client.GET('/explore/communities')
        assert r.code == 200
        assert r.text.count('C++') == 0
        assert 'spammy' not in r.text


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
        response = self.client.POST('/alice/edit/communities',
                                    {'do': 'join:'+self.c_id},
                                    auth_as=self.alice, json=True)

        r = json.loads(response.text)
        assert isinstance(r, dict)

        response = self.client.POST('/alice/edit/communities',
                                    {'do': 'leave:'+self.c_id},
                                    auth_as=self.alice, json=True)

        communities = self.alice.get_communities()
        assert len(communities) == 0


class TestCommunityActions(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant("alice")
        self.bob = self.make_participant("bob")
        self.community = Community.create('test', self.alice)

    def test_post_bad_name_returns_404(self):
        response = self.client.PxST('/for/Bad:Name!/subscribe',
                                    auth_as=self.alice)
        assert response.code == 404

    def test_subscribe_and_unsubscribe(self):
        # Subscribe
        response = self.client.POST('/for/test/subscribe', auth_as=self.bob, json=True)
        assert response.code == 200
        p = self.community.participant.refetch()
        assert p.nsubscribers == 1

        # Subscribe again, shouldn't do anything
        response = self.client.POST('/for/test/subscribe', auth_as=self.bob, json=True)
        assert response.code == 200
        p = self.community.participant.refetch()
        assert p.nsubscribers == 1

        # Unsubscribe
        self.client.POST('/for/test/unsubscribe', auth_as=self.bob, json=True)
        communities = self.bob.get_communities()
        assert len(communities) == 0

    def test_subscribe_and_unsubscribe_as_anon(self):
        response = self.client.POST('/for/test/subscribe', json=True)
        assert response.code == 403

        response = self.client.POST('/for/test/unsubscribe', json=True)
        assert response.code == 403

    def test_join_and_leave(self):
        with self.assertRaises(AuthRequired):
            self.client.POST('/for/test/join')

        self.client.POST('/for/test/join', auth_as=self.bob, json=True)

        communities = self.bob.get_communities()
        assert len(communities) == 1

        self.client.POST('/for/test/leave', auth_as=self.bob, json=True)

        communities = self.bob.get_communities()
        assert len(communities) == 0


class TestCommunityEdit(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant("alice")
        self.community = Community.create('test', self.alice)

    def test_creator_can_edit_community(self):
        data = {'lang': 'en', 'subtitle': '', 'sidebar': ''}
        response = self.client.PxST('/for/test/edit', data, auth_as=self.alice)
        assert response.code == 302

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
        self.alice = self.make_participant('alice')
        self.community = self.alice.create_community('test')
        self.alice.upsert_community_membership(False, self.community.id)

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
        assert len(result['members']) == 0
        assert result['name'] == 'test'

    def test_post_not_supported(self):
        response = self.client.PxST('/for/test/index.json')
        assert response.code == 405

    def test_limit_and_offset(self):
        for i in range(1, 111):
            self.add_participant(str(i))
        response = self.client.GET('/for/test/index.json?limit=10')
        result = json.loads(response.text)
        assert len(result['members']) == 10
        assert result['members'][0]['username'] == '1'
        assert result['members'][-1]['username'] == '10'
        response = self.client.GET('/for/test/index.json?limit=100')
        result = json.loads(response.text)
        assert len(result['members']) == 100
        assert result['members'][0]['username'] == '1'
        assert result['members'][-1]['username'] == '100'
        response = self.client.GET('/for/test/index.json?offset=10')
        result = json.loads(response.text)
        assert len(result['members']) == 10
        assert result['members'][0]['username'] == '11'
        assert result['members'][-1]['username'] == '20'

    def test_invalid_limit(self):
        response = self.client.GxT('/for/test/index.json?limit=abc')
        assert response.code == 400

    def test_invalid_offset(self):
        response = self.client.GxT('/for/test/index.json?offset=abc')
        assert response.code == 400
