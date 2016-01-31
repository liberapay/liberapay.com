from __future__ import print_function, unicode_literals

from liberapay.utils import fake_data
from liberapay.testing import Harness


class TestFakeData(Harness):
    """
    Ensure the fake_data script doesn't throw any exceptions
    """

    def test_fake_data(self):
        num_participants = 5
        num_tips = 5
        num_teams = 1
        num_transfers = 5
        num_communities = 5
        fake_data.populate_db(self.db, num_participants, num_tips, num_teams,
                              num_transfers, num_communities)
        tips = self.db.all("SELECT * FROM tips")
        participants = self.db.all("SELECT * FROM participants")
        transfers = self.db.all("SELECT * FROM transfers")
        assert len(tips) == num_tips
        assert len(participants) == num_participants + num_teams + num_communities
        assert len(transfers) == num_transfers
