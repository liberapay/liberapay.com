from __future__ import print_function, unicode_literals

import json
import itertools

from gittip.models.participant import Participant
from gittip.testing import Harness


class Tests(Harness):

    def setUp(self):
        self._old = Participant._generate_api_key
        seq = itertools.count(0)
        Participant._generate_api_key = lambda self: 'deadbeef{}'.format(next(seq))
        Harness.setUp(self)

    def tearDown(self):
        Participant._generate_api_key = self._old
        Harness.tearDown(self)

    def hit_api_key_json(self, method='GET'):
        method = getattr(self.client, method)
        response = method("/alice/api-key.json", auth_as='alice')
        return json.loads(response.body)['api_key']


    def test_participant_starts_out_with_no_api_key(self):
        alice = self.make_participant('alice', claimed_time='now')
        assert alice.api_key is None

    def test_participant_can_create_a_new_api_key(self):
        self.make_participant('alice', claimed_time='now')
        assert self.hit_api_key_json() == 'deadbeef0'

    def test_participant_attribute_is_updated(self):
        alice = self.make_participant('alice', claimed_time='now')
        alice.recreate_api_key()
        assert alice.api_key == 'deadbeef0'

    def test_participant_can_get_their_api_key(self):
        self.make_participant('alice', claimed_time='now')
        self.hit_api_key_json()
        self.hit_api_key_json()
        self.hit_api_key_json()
        self.hit_api_key_json()
        self.hit_api_key_json()
        self.hit_api_key_json()
        assert self.hit_api_key_json() == 'deadbeef0'

    def test_participant_can_recreate_their_api_key(self):
        self.make_participant('alice', claimed_time='now')
        self.hit_api_key_json('POST')
        self.hit_api_key_json('POST')
        self.hit_api_key_json()
        self.hit_api_key_json('POST')
        self.hit_api_key_json('POST')
        self.hit_api_key_json('POST')
        assert self.hit_api_key_json() == 'deadbeef4'
