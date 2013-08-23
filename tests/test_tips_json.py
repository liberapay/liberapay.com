import datetime
import json
from nose.tools import assert_equal

import pytz

from gittip.testing import Harness
from gittip.testing.client import TestClient


class TestTipsJson(Harness):

    def test_get_response(self):
        client = TestClient()

        now = datetime.datetime.now(pytz.utc)
        self.make_participant("test_tipper", claimed_time=now)

        response = client.get('/test_tipper/tips.json', 'test_tipper')

        assert_equal(response.code, 200) 
        assert_equal(len(json.loads(response.body)), 0) # empty array

    def test_get_response_with_tips(self):
        client = TestClient()

        now = datetime.datetime.now(pytz.utc)
        self.make_participant("test_tippee1", claimed_time=now)
        self.make_participant("test_tipper", claimed_time=now)

        response = client.get('/')
        csrf_token = response.request.context['csrf_token']

        response1 = client.post('/test_tippee1/tip.json',
            {'amount': '1.00', 'csrf_token': csrf_token},
            user='test_tipper')

        response = client.get('/test_tipper/tips.json', 'test_tipper')

        assert_equal(response1.code, 200)
        assert_equal(json.loads(response1.body)['amount'], '1.00')

        data = json.loads(response.body)[0]

        assert_equal(response.code, 200) 
        assert_equal(data['username'], 'test_tippee1')
        assert_equal(data['amount'], '1.00')

    def test_post_bad_platform(self):
        client = TestClient()

        now = datetime.datetime.now(pytz.utc)
        self.make_participant("test_tippee1", claimed_time=now)
        self.make_participant("test_tipper", claimed_time=now)

        response = client.get('/')
        csrf_token = response.request.context['csrf_token']

        response1 = client.post('/test_tipper/tips.json',
            {'0': {'username': 'test_tippee1', 'platform': 'github', 'amount': '1.00', 'csrf_token': csrf_token}},
            user='test_tipper')

        assert_equal(response1.body, "")