from __future__ import unicode_literals

import json

from aspen.utils import utcnow
from gittip.testing import Harness
from gittip.testing.client import TestClient

class TestMembernameJson(Harness):

    def make_client_and_csrf(self):
        client = TestClient()

        csrf_token = client.get('/').request.context['csrf_token']

        return client, csrf_token

    def make_team_and_participant(self):
        self.make_participant("team", claimed_time=utcnow(), number='plural')
        self.make_participant("alice", claimed_time=utcnow())

    def test_post_team_is_not_team_returns_404(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/alice/members/team.json'
            , { 'csrf_token': csrf_token }
            , user='alice'
        )

        actual = response.code
        assert actual == 404

    def test_post_participant_doesnt_exist_returns_404(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/team/members/bob.json'
            , { 'csrf_token': csrf_token }
            , user='team'
        )

        actual = response.code
        assert actual == 404

    def test_post_user_is_not_member_or_team_returns_403(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()
        self.make_participant("bob", claimed_time=utcnow(), number='plural')

        response = client.post('/team/members/alice.json'
            , {
                'take': '0.01'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        actual = response.code
        assert actual == 200

        response = client.post('/team/members/bob.json'
            , {
                'take': '0.01'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        actual = response.code
        assert actual == 200

        response = client.post('/team/members/alice.json'
            , { 'csrf_token': csrf_token }
            , user='bob'
        )

        actual = response.code
        assert actual == 403

    def test_post_take_is_not_decimal_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/team/members/alice.json'
            , {
                'take': 'bad'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        actual = response.code
        assert actual == 400

    def test_post_member_equals_team_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/team/members/team.json'
            , {
                'take': '0.01'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        actual = response.code
        assert actual == 400

    def test_post_take_is_not_zero_or_penny_returns_400(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/team/members/alice.json'
            , {
                'take': '0.02'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        actual = response.code
        assert actual == 400

    def test_post_zero_take_on_non_member_returns_500(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/team/members/alice.json'
            , {
                'take': '0.00'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        actual = response.code
        assert actual == 500

    def test_post_can_add_member_to_team(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/team/members/alice.json'
            , {
                'take': '0.01'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        data = json.loads(response.body)

        actual = len(data)
        assert actual == 2

        for rec in data:
            assert rec['username'] in ('team', 'alice'), rec['username']

    def test_post_can_remove_member_from_team(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/team/members/alice.json'
            , {
                'take': '0.01'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        data = json.loads(response.body)

        actual = len(data)
        assert actual == 2

        for rec in data:
            assert rec['username'] in ('team', 'alice'), rec['username']

        response = client.post('/team/members/alice.json'
            , {
                'take': '0.00'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        data = json.loads(response.body)

        actual = len(data)
        assert actual == 1

        actual = data[0]['username']
        assert actual == 'team'

    def test_post_non_team_member_adds_member_returns_403(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()
        self.make_participant("bob", claimed_time=utcnow())

        response = client.post('/team/members/alice.json'
            , {
                'take': '0.01'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        actual = response.code
        assert actual == 200

        response = client.post('/team/members/bob.json'
            , {
                'take': '0.01'
              , 'csrf_token': csrf_token
            }
            , user='alice'
        )

        actual = response.code
        assert actual == 403

    def test_get_team_when_team_equals_member(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.get('/team/members/team.json', 'team')

        data = json.loads(response.body)

        actual = response.code
        assert actual == 200

        actual = data['username']
        assert actual == 'team'

    def test_get_team_member_returns_null_when_non_member(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.get('/team/members/alice.json', 'team')

        actual = response.code
        assert actual == 200

        actual = response.body
        assert actual == 'null'

    def test_get_team_members_returns_take_when_member(self):
        client, csrf_token = self.make_client_and_csrf()

        self.make_team_and_participant()

        response = client.post('/team/members/alice.json'
            , {
                'take': '0.01'
              , 'csrf_token': csrf_token
            }
            , user='team'
        )

        actual = response.code
        assert actual == 200

        response = client.get('/team/members/alice.json', 'team')

        data = json.loads(response.body)

        actual = response.code
        assert actual == 200

        actual = data['username']
        assert actual == 'alice'

        actual = data['take']
        assert actual == '0.01'
