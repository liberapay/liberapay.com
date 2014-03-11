from __future__ import unicode_literals

import pytest
from aspen import json
from aspen.utils import utcnow
from gittip.testing import Harness

class TestMembernameJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.make_participant("team", claimed_time=utcnow(), number='plural')
        self.make_participant("alice", claimed_time=utcnow())

    def test_post_team_is_not_team_returns_404(self):
        response = self.client.PxST('/alice/members/team.json', auth_as='alice')
        assert response.code == 404

    def test_post_participant_doesnt_exist_returns_404(self):
        response = self.client.PxST('/team/members/bob.json', auth_as='team')
        assert response.code == 404

    def test_post_user_is_not_member_or_team_returns_403(self):
        self.make_participant("bob", claimed_time=utcnow(), number='plural')
        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as='team')
        assert response.code == 200

        response = self.client.POST('/team/members/bob.json', {'take': '0.01'}, auth_as='team')
        assert response.code == 200

        response = self.client.PxST('/team/members/alice.json', auth_as='bob')
        assert response.code == 403

    def test_post_take_is_not_decimal_returns_400(self):
        response = self.client.PxST('/team/members/alice.json', {'take': 'bad'}, auth_as='team')
        assert response.code == 400

    def test_post_member_equals_team_returns_400(self):
        response = self.client.PxST('/team/members/team.json', {'take': '0.01'}, auth_as='team')
        assert response.code == 400

    def test_post_take_is_not_zero_or_penny_returns_400(self):
        response = self.client.PxST('/team/members/alice.json', {'take': '0.02'}, auth_as='team')
        assert response.code == 400

    def test_post_zero_take_on_non_member_raises_Exception(self):
        pytest.raises( Exception
                     , self.client.PxST
                     , '/team/members/alice.json'
                     , {'take': '0.00'}
                     , auth_as='team'
                      )

    def test_post_can_add_member_to_team(self):
        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as='team')
        data = json.loads(response.body)
        assert len(data) == 2

        for rec in data:
            assert rec['username'] in ('team', 'alice'), rec['username']

    def test_post_can_remove_member_from_team(self):
        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as='team')

        data = json.loads(response.body)
        assert len(data) == 2

        for rec in data:
            assert rec['username'] in ('team', 'alice'), rec['username']

        response = self.client.POST('/team/members/alice.json', {'take': '0.00'}, auth_as='team')

        data = json.loads(response.body)
        assert len(data) == 1
        assert data[0]['username'] == 'team'

    def test_post_non_team_member_adds_member_returns_403(self):
        self.make_participant("bob", claimed_time=utcnow())

        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as='team')
        assert response.code == 200

        response = self.client.PxST('/team/members/bob.json', {'take': '0.01'}, auth_as='alice')
        assert response.code == 403

    def test_get_team_when_team_equals_member(self):
        response = self.client.GET('/team/members/team.json', auth_as='team')
        data = json.loads(response.body)
        assert response.code == 200
        assert data['username'] == 'team'

    def test_get_team_member_returns_null_when_non_member(self):
        response = self.client.GET('/team/members/alice.json', auth_as='team')
        assert response.code == 200
        assert response.body == 'null'

    def test_get_team_members_returns_take_when_member(self):
        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as='team')
        assert response.code == 200

        response = self.client.GET('/team/members/alice.json', auth_as='team')
        data = json.loads(response.body)

        assert response.code == 200
        assert data['username'] == 'alice'
        assert data['take'] == '0.01'
