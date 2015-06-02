from __future__ import unicode_literals

import pytest
from aspen import json
from liberapay.testing import Harness

xfail = pytest.mark.xfail

class TestMembernameJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.team = self.make_participant("team", kind='group')
        self.alice = self.make_participant("alice")

    @xfail
    def test_post_participant_doesnt_exist_returns_404(self):
        response = self.client.PxST('/team/members/bob.json', auth_as=self.team)
        assert response.code == 404

    @xfail
    def test_post_user_is_not_member_or_team_returns_403(self):
        bob = self.make_participant("bob", kind='group')
        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as=self.team)
        assert response.code == 200

        response = self.client.POST('/team/members/bob.json', {'take': '0.01'}, auth_as=self.team)
        assert response.code == 200

        response = self.client.PxST('/team/members/alice.json', auth_as=bob)
        assert response.code == 403

    def test_post_take_is_not_decimal_returns_400(self):
        response = self.client.PxST('/team/members/alice.json', {'take': 'bad'}, auth_as=self.alice)
        assert response.code == 400

    @xfail
    def test_post_member_equals_team_returns_400(self):
        response = self.client.PxST('/team/members/team.json', {'take': '0.01'}, auth_as=self.team)
        assert response.code == 400

    @xfail
    def test_post_take_is_not_zero_or_penny_returns_400(self):
        response = self.client.PxST('/team/members/alice.json', {'take': '0.02'}, auth_as=self.team)
        assert response.code == 403

    @xfail
    def test_post_zero_take_on_non_member_raises_Exception(self):
        response = self.client.PxST('/team/members/alice.json', {'take': '0.00'}, auth_as=self.team)
        assert response.code == 403

    @xfail
    def test_post_can_add_member_to_team(self):
        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as=self.team)
        data = json.loads(response.body)['members']
        assert len(data) == 2

        for rec in data:
            assert rec['username'] in ('team', 'alice'), rec['username']

    @xfail
    def test_post_can_remove_member_from_team(self):
        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as=self.team)

        data = json.loads(response.body)['members']
        assert len(data) == 2

        for rec in data:
            assert rec['username'] in ('team', 'alice'), rec['username']

        response = self.client.POST('/team/members/alice.json',
                                    {'take': '0.00', 'confirmed': True},
                                    auth_as=self.team)
        data = json.loads(response.body)['members']
        assert len(data) == 1
        assert data[0]['username'] == 'team'

    @xfail
    def test_post_non_team_member_adds_member_returns_403(self):
        self.make_participant("bob")

        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as=self.team)
        assert response.code == 200

        response = self.client.PxST('/team/members/bob.json', {'take': '0.01'}, auth_as=self.alice)
        assert response.code == 403

    def test_get_team_when_team_equals_member(self):
        response = self.client.GET('/team/members/team.json')
        data = json.loads(response.body)
        assert response.code == 200
        assert data['username'] == 'team'
        assert data['take'] == '0.00'

    def test_get_team_member_returns_null_when_non_member(self):
        response = self.client.GET('/team/members/alice.json')
        assert response.code == 200
        assert response.body == 'null'

    @xfail
    def test_get_team_members_returns_take_when_member(self):
        response = self.client.POST('/team/members/alice.json', {'take': '0.01'}, auth_as=self.team)
        assert response.code == 200

        response = self.client.GET('/team/members/alice.json', auth_as=self.team)
        data = json.loads(response.body)
        assert response.code == 200
        assert data['username'] == 'alice'
        assert data['take'] == '0.01'

    @xfail
    def test_preclude_adding_stub_participants(self):
        self.make_stub(username="stub")
        response = self.client.PxST('/team/members/stub.json', {'take': '0.01'}, auth_as=self.team)
        assert response.code == 403
