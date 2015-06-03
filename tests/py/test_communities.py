from __future__ import absolute_import, division, print_function, unicode_literals

import json

from liberapay.models.community import Community, slugize
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Alice joins a community.
        self.alice = self.make_participant("alice", last_bill_result='')
        self.client.POST( '/for/communities.json'
                        , {'name': 'something', 'is_member': 'true'}
                        , auth_as=self.alice
                         )

    def test_community_member_shows_up_on_community_listing(self):
        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 2  # entry in New Participants

    def test_givers_show_up_on_community_page(self):

        # Alice tips bob.
        bob = self.make_participant('bob')
        self.alice.set_tip_to(bob, '1.00')

        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 4  # entries in both New Participants and Givers
        assert 'bob' not in html

    def test_givers_dont_show_up_if_they_give_zero(self):

        # Alice tips bob.
        bob = self.make_participant('bob')
        self.alice.set_tip_to(bob, '1.00')
        self.alice.set_tip_to(bob, '0.00')

        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 2  # entry in New Participants only
        assert 'bob' not in html

    def test_receivers_show_up_on_community_page(self):

        # Bob tips alice.
        bob = self.make_participant("bob", last_bill_result='')
        bob.set_tip_to(self.alice, '1.00')

        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 4  # entries in both New Participants and Receivers
        assert 'bob' not in html

    def test_receivers_dont_show_up_if_they_receive_zero(self):

        # Bob tips alice.
        bob = self.make_participant("bob", last_bill_result='')
        bob.set_tip_to(self.alice, '1.00')
        bob.set_tip_to(self.alice, '0.00')  # zero out bob's tip

        html = self.client.GET('/for/something/', want='response.body')
        assert html.count('alice') == 2  # entry in New Participants only
        assert 'bob' not in html

    def test_community_listing_works_for_pristine_community(self):
        html = self.client.GET('/for/pristine/', want='response.body')
        assert 'first one here' in html


class TestCommunitiesJson(Harness):

    def test_post_name_pattern_none_returns_400(self):
        response = self.client.PxST('/for/communities.json', {'name': 'BadName!'})
        assert response.code == 400

    def test_post_is_member_not_bool_returns_400(self):
        response = self.client.PxST( '/for/communities.json'
                                   , {'name': 'Good Name', 'is_member': 'no'}
                                    )
        assert response.code == 400

    def test_joining_and_leaving_community(self):
        alice = self.make_participant("alice")

        response = self.client.GET('/for/communities.json', auth_as=alice)
        assert len(json.loads(response.body)['communities']) == 0

        response = self.client.POST( '/for/communities.json'
                                   , {'name': 'Test', 'is_member': 'true'}
                                   , auth_as=alice
                                    )

        communities = json.loads(response.body)['communities']
        assert len(communities) == 1
        assert communities[0]['name'] == 'Test'
        assert communities[0]['nmembers'] == 1

        response = self.client.POST( '/for/communities.json'
                                   , {'name': 'Test', 'is_member': 'false'}
                                   , auth_as=alice
                                    )

        response = self.client.GET('/for/communities.json', auth_as=alice)

        assert len(json.loads(response.body)['communities']) == 0

        # Check that the empty community was deleted
        community = Community.from_slug('test')
        assert not community

    def test_get_can_get_communities_for_user(self):
        alice = self.make_participant("alice")
        response = self.client.GET('/for/communities.json', auth_as=alice)
        assert len(json.loads(response.body)['communities']) == 0

    def test_get_can_get_communities_when_anon(self):
        response = self.client.GET('/for/communities.json')

        assert response.code == 200
        assert len(json.loads(response.body)['communities']) == 0


class TestForCommunityJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.add_participant('alice')
        self.add_participant('bob')
        carl = self.add_participant('carl')
        carl.insert_into_communities(False, 'test', 'test')

    def add_participant(self, participant_name):
        participant = self.make_participant(participant_name)
        participant.insert_into_communities(True, 'test', slugize('test'))
        return participant

    def test_get_non_existing_community(self):
        response = self.client.GxT('/for/NonExisting/index.json')
        assert response.code == 404

    def test_get_existing_community(self):
        response = self.client.GET('/for/test/index.json')
        result = json.loads(response.body)
        assert len(result['members']) == 2
        assert result['name'] == 'test'

    def test_post_not_supported(self):
        response = self.client.PxST('/for/test/index.json')
        assert response.code == 405

    def test_limit(self):
        response = self.client.GET('/for/test/index.json?limit=1')
        result = json.loads(response.body)
        assert len(result['members']) == 1

    def test_offset(self):
        response = self.client.GET('/for/test/index.json?offset=1')
        result = json.loads(response.body)
        assert len(result['members']) == 1

    def test_max_limit(self):
        for i in range(110):
            self.add_participant(str(i))
        response = self.client.GET('/for/test/index.json?limit=200')
        result = json.loads(response.body)
        assert len(result['members']) == 100

    def test_invalid_limit(self):
        response = self.client.GxT('/for/test/index.json?limit=abc')
        assert response.code == 400

    def test_invalid_offset(self):
        response = self.client.GxT('/for/test/index.json?offset=abc')
        assert response.code == 400
