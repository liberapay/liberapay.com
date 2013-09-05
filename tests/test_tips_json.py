from __future__ import print_function, unicode_literals

import datetime
import json
from nose.tools import assert_equal, assert_true

import pytz
import base64

from gittip.testing import Harness
from gittip.testing.client import TestClient


class TestTipsJson(Harness):

    def also_prune_variant(self, also_prune, tippees=1):
        client = TestClient()

        now = datetime.datetime.now(pytz.utc)
        self.make_participant("test_tippee1", claimed_time=now)
        self.make_participant("test_tippee2", claimed_time=now)
        self.make_participant("test_tipper", claimed_time=now)

        api_key = json.loads(client.get('/test_tipper/api-key.json', 'test_tipper').body)['api_key']

        data = [
            {'username': 'test_tippee1', 'platform': 'gittip', 'amount': '1.00'},
            {'username': 'test_tippee2', 'platform': 'gittip', 'amount': '2.00'}
        ]

        response = client.post( '/test_tipper/tips.json'
                              , json.dumps(data)
                              , user='test_tipper'
                              , content_type='application/json'
                              , HTTP_AUTHORIZATION='Basic ' + base64.b64encode(api_key + ':')
                               )

        assert_equal(response.code, 200)
        assert_equal(len(json.loads(response.body)), 2)

        response = client.post( '/test_tipper/tips.json?also_prune=' + also_prune
                              , json.dumps([{ 'username': 'test_tippee2'
                                            , 'platform': 'gittip'
                                            , 'amount': '1.00'
                                             }])
                              , user='test_tipper'
                              , content_type='application/json'
                              , HTTP_AUTHORIZATION='Basic ' + base64.b64encode(api_key + ':')
                               )

        assert_equal(response.code, 200)

        response = client.get('/test_tipper/tips.json', 'test_tipper')
        assert_equal(response.code, 200)
        assert_equal(len(json.loads(response.body)), tippees)

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

        api_key = json.loads(client.get('/test_tipper/api-key.json', 'test_tipper').body)['api_key']

        response = client.post( '/test_tipper/tips.json'
                              , json.dumps([{ 'username': 'test_tippee1'
                                            , 'platform': 'badname'
                                            , 'amount': '1.00'
                                             }])
                              , user='test_tipper'
                              , content_type='application/json'
                              , HTTP_AUTHORIZATION='Basic ' + base64.b64encode(api_key + ':')
                               )

        assert_equal(response.code, 200)

        resp = json.loads(response.body)

        for tip in resp:
            assert_true('error' in tip)

    def test_also_prune_as_1(self):
        self.also_prune_variant('1')

    def test_also_prune_as_true(self):
        self.also_prune_variant('true')

    def test_also_prune_as_yes(self):
        self.also_prune_variant('yes')

    def test_also_prune_as_0(self):
        self.also_prune_variant('0', 2)
