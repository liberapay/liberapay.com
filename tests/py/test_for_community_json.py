from gittip.testing import Harness

import json

class TestForCommunityJson(Harness):

    def setUp(self):
        Harness.setUp(self)

        self.community = 'Test'
        self.alice = self.make_participant('alice')

        self.client.POST( '/for/communities.json'
                           , {'name': self.community, 'is_member': 'true'}
                           , auth_as='alice'
                            )

    def test_get_non_existing_community(self):
        response = self.client.GxT('/for/NonExisting/index.json')
        assert response.code == 404

    def test_get_existing_community(self):
        response = self.client.GET('/for/Test/index.json')
        result = json.loads(response.body)

        assert len(result["members"]) == 1
        assert result["name"] == "Test"

    def test_post_not_supported(self):
        response = self.client.PxST('/for/Test/index.json')
        assert response.code == 405
