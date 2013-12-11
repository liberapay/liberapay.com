from __future__ import print_function, unicode_literals

import datetime
import json

import pytz

from gittip.testing import Harness


class TestTipJson(Harness):

    def test_get_amount_and_total_back_from_api(self):
        "Test that we get correct amounts and totals back on POSTs to tip.json"

        # First, create some test data
        # We need accounts
        now = datetime.datetime.now(pytz.utc)
        self.make_participant("test_tippee1", claimed_time=now)
        self.make_participant("test_tippee2", claimed_time=now)
        self.make_participant("test_tipper")

        # Then, add a $1.50 and $3.00 tip
        response1 = self.client.POST( "/test_tippee1/tip.json"
                                    , {'amount': "1.00"}
                                    , auth_as='test_tipper'
                                     )

        response2 = self.client.POST( "/test_tippee2/tip.json"
                                    , {'amount': "3.00"}
                                    , auth_as='test_tipper'
                                     )

        # Confirm we get back the right amounts.
        first_data = json.loads(response1.body)
        second_data = json.loads(response2.body)
        assert first_data['amount'] == "1.00"
        assert first_data['total_giving'] == "1.00"
        assert second_data['amount'] == "3.00"
        assert second_data['total_giving'] == "4.00"

    def test_set_tip_out_of_range(self):
        now = datetime.datetime.now(pytz.utc)
        self.make_participant("alice", claimed_time=now)
        self.make_participant("bob", claimed_time=now)

        response = self.client.PxST( "/alice/tip.json"
                                   , {'amount': "110.00"}
                                   , auth_as='bob'
                                    )
        assert "bad amount" in response.body
        assert response.code == 400

        response = self.client.PxST( "/alice/tip.json"
                                   , {'amount': "-1.00"}
                                   , auth_as='bob'
                                    )
        assert "bad amount" in response.body
        assert response.code == 400
