from __future__ import unicode_literals

from gittip.models.participant import Participant
from gittip.testing import Harness


class Tests(Harness):

    def test_ride_free_json_rides_free(self):
        self.make_participant('alice', claimed_time='now', last_bill_result='')
        response = self.client.PxST("/ride-free.json", auth_as='alice')
        assert response.code == 204
        assert Participant.from_username('alice').rides_free
