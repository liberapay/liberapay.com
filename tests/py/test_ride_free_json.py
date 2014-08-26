from __future__ import unicode_literals

from gratipay.models.participant import Participant
from gratipay.testing import Harness


class Tests(Harness):

    def test_ride_free_json_sets_is_free_rider_to_true(self):
        self.make_participant('alice', claimed_time='now', last_bill_result='')
        response = self.client.PxST("/ride-free.json", auth_as='alice')
        assert response.code == 204
        assert Participant.from_username('alice').is_free_rider
