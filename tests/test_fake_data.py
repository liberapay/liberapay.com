from gittip.testing import Harness
from gittip import fake_data
from gittip.models.tip import Tip
from gittip.models.participant import Participant


class TestFakeData(Harness):
    """
    Ensure the fake_data script doesn't throw any exceptions
    """

    def setUp(self):
        super(Harness, self).setUp()

    def test_fake_data(self):
        num_participants = 5
        num_tips = 5
        fake_data.populate_db(self.session, num_participants, num_tips)
        tips = Tip.query.all()
        participants = Participant.query.all()
        assert len(tips) == num_tips
        assert len(participants) == num_participants

