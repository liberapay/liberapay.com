from __future__ import absolute_import, division, print_function, unicode_literals

import json

from gittip.testing import Harness


class Tests(Harness):

    def test_delete_nonexistent(self):
        self.make_participant('alice', claimed_time='now', elsewhere='twitter')
        response = self.client.PxST('/alice/delete-elsewhere.json', {'platform': 'twitter', 'user_id': 'nonexistent'}, auth_as='alice')
        assert response.code == 400
        assert "not exist" in response.body

    def test_delete_last(self):
        platform, user_id = 'twitter', '1'
        self.make_elsewhere(platform, user_id, 'alice').opt_in('alice')
        data = dict(platform=platform, user_id=user_id)
        response = self.client.PxST('/alice/delete-elsewhere.json', data, auth_as='alice')
        assert response.code == 400
        assert "last login" in response.body

    def test_delete_last_login(self):
        platform, user_id = 'twitter', '1'
        alice, _ = self.make_elsewhere(platform, user_id, 'alice').opt_in('alice')
        self.make_elsewhere('venmo', '1', 'alice')
        alice.participant.take_over(('venmo', '1'))
        data = dict(platform=platform, user_id=user_id)
        response = self.client.PxST('/alice/delete-elsewhere.json', data, auth_as='alice')
        assert response.code == 400
        assert "last login" in response.body

    def test_delete_200(self):
        platform, user_id = 'twitter', '1'
        alice, _ = self.make_elsewhere(platform, user_id, 'alice').opt_in('alice')
        self.make_elsewhere('github', '1', 'alice')
        alice.participant.take_over(('github', '1'))
        data = dict(platform=platform, user_id=user_id)
        response = self.client.POST('/alice/delete-elsewhere.json', data, auth_as='alice')
        assert response.code == 200
        msg = json.loads(response.body)['msg']
        assert "OK" in msg
