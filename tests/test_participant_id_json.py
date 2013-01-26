import json

from gittip.testing import Harness
from gittip.testing.client import TestClient


class TestParticipantIdJson(Harness):

    def change_id(self, new_id, user='alice'):
        self.make_participant('alice')

        client = TestClient()
        response = client.get('/')
        csrf_token = response.request.context['csrf_token']

        response = client.post( "/alice/participant_id.json"
                              , { 'participant_id': new_id
                                , 'csrf_token': csrf_token
                                 }
                              , user=user
                               )
        return response


    def test_participant_can_change_their_id(self):
        response = self.change_id("bob")
        actual = json.loads(response.body)['participant_id']
        assert actual == "bob", actual

    def test_anonymous_gets_404(self):
        response = self.change_id("bob", user=None)
        assert response.code == 404, response.code

    def test_invalid_is_400(self):
        response = self.change_id("\u2034")
        assert response.code == 400, response.code

    def test_restricted_id_is_400(self):
        response = self.change_id("assets")
        assert response.code == 400, response.code

    def test_unavailable_is_409(self):
        self.make_participant("bob")
        response = self.change_id("bob")
        assert response.code == 409, response.code

    def test_too_long_is_413(self):
        self.make_participant("bob")
        response = self.change_id("I am way too long, and you know it, "
                                  "and I know it, and the American people "
                                  "know it.")
        assert response.code == 413, response.code
