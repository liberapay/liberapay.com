from __future__ import unicode_literals

import json

from gittip.testing import Harness

class TestMembernameJson(Harness):

    def change_email_address(self, address, user='alice', should_fail=True):
        self.make_participant("alice")

        if should_fail:
            response = self.client.PxST("/alice/email.json"
                , {'email': address,}
                , auth_as=user
            )
        else:
            response = self.client.POST("/alice/email.json"
                , {'email': address,}
                , auth_as=user
            )
        return response

    def test_participant_can_change_email(self):
        response = self.change_email_address('alice@gittip.com', should_fail=False)
        actual = json.loads(response.body)['email']
        assert actual == 'alice@gittip.com', actual

    def test_post_anon_returns_404(self):
        response = self.change_email_address('anon@gittip.com', user=None)
        assert response.code == 404, response.code

    def test_post_with_no_at_symbol_is_400(self):
        response = self.change_email_address('gittip.com')
        assert response.code == 400, response.code

    def test_post_with_no_period_symbol_is_400(self):
        response = self.change_email_address('test@gittip')
        assert response.code == 400, response.code
