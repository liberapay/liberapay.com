from gittip.testing import Harness

import json
from gittip.models.community import slugize

class TestForCommunityJson(Harness):

    def setUp(self):
        Harness.setUp(self)

        self.alice = self.make_participant('alice')
        self.alice.insert_into_communities(True, 'test', slugize('test'))

    def test_get_non_existing_community(self):
        response = self.client.GxT('/for/NonExisting/index.json')
        assert response.code == 404

    def test_get_existing_community(self):
        response = self.client.GET('/for/test/index.json')
        result = json.loads(response.body)

        assert len(result["members"]) == 1
        assert result["name"] == "test"

    def test_post_not_supported(self):
        response = self.client.PxST('/for/test/index.json')
        assert response.code == 405
