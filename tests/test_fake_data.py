from __future__ import print_function, unicode_literals

from gittip import fake_data
from gittip.testing import Harness


class TestFakeData(Harness):
    """
    Ensure the fake_data script doesn't throw any exceptions
    """

    def setUp(self):
        super(Harness, self).setUp()

    def test_fake_data(self):
        num_participants = 5
        num_tips = 5
        num_teams = 1
        fake_data.populate_db(self.session, num_participants, num_tips, num_teams)
        tips =
        participants =
        assert len(tips) == num_tips
        assert len(participants) == num_participants + num_teams

