from __future__ import absolute_import, division, print_function, unicode_literals

import json

from liberapay.testing import Harness


class Tests(Harness):

    def test_delete_nonexistent(self):
        alice = self.make_participant('alice', elsewhere='twitter')
        response = self.client.PxST('/alice/delete-elsewhere.json', {'platform': 'twitter', 'user_id': 'nonexistent'}, auth_as=alice)
        assert response.code == 400
        assert "not exist" in response.body

    def test_delete_200(self):
        platform = 'twitter'
        alice = self.make_participant('alice', elsewhere=platform)
        self.make_elsewhere('github', '1', 'alice')
        alice.take_over(('github', '1'))
        data = dict(platform=platform, user_id=alice.id)
        response = self.client.POST('/alice/delete-elsewhere.json', data, auth_as=alice)
        assert response.code == 200
        msg = json.loads(response.body)['msg']
        assert "OK" in msg
