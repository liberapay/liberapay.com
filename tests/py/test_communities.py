from __future__ import absolute_import, division, print_function, unicode_literals

import json

from liberapay.models.community import Community
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Alice joins a community.
        self.alice = self.make_participant('alice', balance=100)
        c = self.alice.create_community('something')
        self.alice.update_community_status('memberships', True, c.id)

    def test_community_member_shows_up_on_community_listing(self):
        html = self.client.GET('/for/something/').text
        assert html.count('alice') == 2  # entry in New Participants


class TestCommunitiesJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant("alice")
        self.c_id = str(self.alice.create_community('test').id)

    def test_post_bad_id_returns_400(self):
        response = self.client.PxST('/alice/communities.json',
                                    {'do': 'join:NaN'},
                                    auth_as=self.alice)
        assert response.code == 400

    def test_joining_and_leaving_community(self):
        response = self.client.POST( '/alice/communities.json'
                                   , {'do': 'join:'+self.c_id}
                                   , auth_as=self.alice
                                   , xhr=True
                                    )

        r = json.loads(response.body)
        assert r == {}

        response = self.client.POST( '/alice/communities.json'
                                   , {'do': 'leave:'+self.c_id}
                                   , auth_as=self.alice
                                   , xhr=True
                                    )

        response = self.client.GET('/alice/communities.json', auth_as=self.alice)

        assert len(json.loads(response.body)) == 0

    def test_get_can_get_communities_for_user(self):
        response = self.client.GET('/alice/communities.json', auth_as=self.alice)
        assert len(json.loads(response.body)) == 0


class TestCommunitySubscriptions(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant("alice")
        self.community = Community.create('test', self.alice.id)

    def test_post_bad_name_returns_404(self):
        response = self.client.PxST('/for/Bad:Name!/subscribe',
                                    auth_as=self.alice)
        assert response.code == 404

    def test_subscribe_and_unsubscribe(self):
        response = self.client.POST('/for/test/subscribe', auth_as=self.alice,
                                    xhr=True)

        r = json.loads(response.body)
        assert r == {}

        response = self.client.POST('/for/test/unsubscribe', auth_as=self.alice,
                                    xhr=True)

        response = self.client.GET('/alice/communities.json', auth_as=self.alice)

        assert len(json.loads(response.body)) == 0


class TestForCommunityJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        alice = self.make_participant('alice')
        self.community = alice.create_community('test')
        alice.update_community_status('memberships', True, self.community.id)
        self.add_participant('bob')
        carl = self.add_participant('carl')
        carl.update_community_status('memberships', False, self.community.id)

    def add_participant(self, participant_name):
        participant = self.make_participant(participant_name)
        participant.update_community_status('memberships', True, self.community.id)
        return participant

    def test_get_non_existing_community(self):
        response = self.client.GxT('/for/NonExisting/index.json')
        assert response.code == 404

    def test_get_existing_community(self):
        response = self.client.GET('/for/test/index.json')
        result = json.loads(response.body)
        #assert len(result['animators']) == 2  # Not implemented yet
        assert result['name'] == 'test'

    def test_post_not_supported(self):
        response = self.client.PxST('/for/test/index.json')
        assert response.code == 405

    def test_limit(self):
        response = self.client.GET('/for/test/index.json?limit=1')
        json.loads(response.body)
        #assert len(result['animators']) == 1  # Not implemented yet

    def test_offset(self):
        response = self.client.GET('/for/test/index.json?offset=1')
        json.loads(response.body)
        #assert len(result['animators']) == 1  # Not implemented yet

    def test_max_limit(self):
        for i in range(110):
            self.add_participant(str(i))
        response = self.client.GET('/for/test/index.json?limit=200')
        json.loads(response.body)
        #assert len(result['animators']) == 100  # Not implemented yet

    def test_invalid_limit(self):
        response = self.client.GxT('/for/test/index.json?limit=abc')
        assert response.code == 400

    def test_invalid_offset(self):
        response = self.client.GxT('/for/test/index.json?offset=abc')
        assert response.code == 400
