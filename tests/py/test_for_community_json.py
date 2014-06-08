import json

from gittip.models.community import slugize
from gittip.testing import Harness


class TestForCommunityJson(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.add_participant('alice')
        self.add_participant('bob')

    def add_participant(self, participant_name):
        participant = self.make_participant(participant_name)
        participant.insert_into_communities(True, 'test', slugize('test'))

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

    def test_invalid_limit(self):
        response = self.client.GxT('/for/test/index.json?limit=abc')
        assert response.code == 400

    def test_invalid_offset(self):
        response = self.client.GxT('/for/test/index.json?offset=abc')
        assert response.code == 400
