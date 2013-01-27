import datetime
import json
from nose.tools import assert_equal

import pytz

from gittip.testing import Harness
from gittip.testing.client import TestClient


class TestTipJson(Harness):

    def test_get_amount_and_total_back_from_api(self):
        "Test that we get correct amounts and totals back on POSTs to tip.json"
        client = TestClient()

        # First, create some test data
        # We need accounts
        now = datetime.datetime.now(pytz.utc)
        self.make_participant("test_tippee1", claimed_time=now)
        self.make_participant("test_tippee2", claimed_time=now)
        self.make_participant("test_tipper")

        # We need to get ourselves a token!
        response = client.get('/')
        csrf_token = response.request.context['csrf_token']

        # Then, add a $1.50 and $3.00 tip
        response1 = client.post("/test_tippee1/tip.json",
                                {'amount': "1.00", 'csrf_token': csrf_token},
                                user='test_tipper')

        response2 = client.post("/test_tippee2/tip.json",
                                {'amount': "3.00", 'csrf_token': csrf_token},
                                user='test_tipper')

        # Confirm we get back the right amounts.
        first_data = json.loads(response1.body)
        second_data = json.loads(response2.body)
        assert_equal(first_data['amount'], "1.00")
        assert_equal(first_data['total_giving'], "1.00")
        assert_equal(second_data['amount'], "3.00")
        assert_equal(second_data['total_giving'], "4.00")
