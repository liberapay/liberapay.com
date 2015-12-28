from __future__ import absolute_import, division, print_function, unicode_literals

import json

from liberapay.models.community import Community, slugize
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Alice joins a community.
        self.alice = self.make_participant('alice', balance=100)
        self.client.POST('/alice/communities.json', {'do': 'join:something'},
                         auth_as=self.alice, xhr=True)

    def test_community_member_shows_up_on_community_listing(self):
        html = self.client.GET('/for/something/').text
        assert html.count('alice') == 2  # entry in New Participants

    def test_givers_show_up_on_community_page(self):

        # Alice tips bob.
        bob = self.make_participant('bob')
        self.alice.set_tip_to(bob, '1.00')

        html = self.client.GET('/for/something/').text
        assert html.count('alice') == 4, html  # entries in both New Participants and Givers
        assert 'bob' not in html, html

    def test_givers_dont_show_up_if_they_give_zero(self):

        # Alice tips bob.
        bob = self.make_participant('bob')
        self.alice.set_tip_to(bob, '1.00')
        self.alice.set_tip_to(bob, '0.00')

        html = self.client.GET('/for/something/').text
        assert html.count('alice') == 2  # entry in New Participants only
        assert 'bob' not in html

    def test_receivers_show_up_on_community_page(self):

        # Bob tips alice.
        bob = self.make_participant('bob', balance=100)
        bob.set_tip_to(self.alice, '1.00')

        html = self.client.GET('/for/something/').text
        assert html.count('alice') == 4  # entries in both New Participants and Receivers
        assert 'bob' not in html

    def test_receivers_dont_show_up_if_they_receive_zero(self):

        # Bob tips alice.
        bob = self.make_participant('bob', balance=100)
        bob.set_tip_to(self.alice, '1.00')
        bob.set_tip_to(self.alice, '0.00')  # zero out bob's tip

        html = self.client.GET('/for/something/').text
        assert html.count('alice') == 2  # entry in New Participants only
        assert 'bob' not in html

    def test_community_listing_works_for_pristine_community(self):
        html = self.client.GET('/for/pristine/').text
        assert 'first one here' in html


class TestCommunitiesJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice = self.make_participant("alice")

    def test_post_bad_name_returns_400(self):
        response = self.client.PxST('/alice/communities.json',
                                    {'do': 'join:Bad:Name!'},
                                    auth_as=self.alice)
        assert response.code == 400

    def test_joining_and_leaving_community(self):
        response = self.client.POST( '/alice/communities.json'
                                   , {'do': 'join:Test'}
                                   , auth_as=self.alice
                                   , xhr=True
                                    )

        r = json.loads(response.body)
        assert r['slug'] == 'test'

        response = self.client.POST( '/alice/communities.json'
                                   , {'do': 'leave:Test'}
                                   , auth_as=self.alice
                                   , xhr=True
                                    )

        response = self.client.GET('/alice/communities.json', auth_as=self.alice)

        assert len(json.loads(response.body)) == 0

        # Check that the empty community was deleted
        community = Community.from_slug('test')
        assert not community

    def test_get_can_get_communities_for_user(self):
        response = self.client.GET('/alice/communities.json', auth_as=self.alice)
        assert len(json.loads(response.body)) == 0


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
