import pytest
from liberapay.testing import Harness
from liberapay.models.participant import Participant
from datetime import timedelta
from liberapay.i18n.currencies import Money

class TestIncomeGoalChecks(Harness):

    def setUp(self):
        super(TestIncomeGoalChecks, self).setUp()
        self.alice = self.make_participant('alice', weekly_income_goal=Money('100.00', 'EUR'))
        self.db.run("""
            INSERT INTO transfers (recipient, amount, timestamp)
            VALUES (%s, %s, %s)
        """, (self.alice.id, Money('25.00', 'EUR'), self.utcnow() - timedelta(weeks=1)))
        self.db.run("""
            INSERT INTO transfers (recipient, amount, timestamp)
            VALUES (%s, %s, %s)
        """, (self.alice.id, Money('25.00', 'EUR'), self.utcnow() - timedelta(weeks=2)))
        self.db.run("""
            INSERT INTO transfers (recipient, amount, timestamp)
            VALUES (%s, %s, %s)
        """, (self.alice.id, Money('25.00', 'EUR'), self.utcnow() - timedelta(weeks=3)))
        self.db.run("""
            INSERT INTO transfers (recipient, amount, timestamp)
            VALUES (%s, %s, %s)
        """, (self.alice.id, Money('25.00', 'EUR'), self.utcnow() - timedelta(weeks=4)))

    def test_income_goal_met_and_notification_sent(self):
        # Test income goal met and notification sent correctly
        self.alice.check_income_goals()
        assert self.db.one("""
            SELECT EXISTS(
                SELECT 1 FROM income_notifications
                WHERE user_id = %s
            )
        """, (self.alice.id,)) is True

    def test_income_goal_not_met(self):
        # Adjust one payment to simulate failing to meet the goal
        self.db.run("""
            UPDATE transfers SET amount = %s WHERE timestamp = %s
        """, (Money('15.00', 'EUR'), self.utcnow() - timedelta(weeks=1)))
        self.alice.check_income_goals()
        assert self.db.one("""
            SELECT EXISTS(
                SELECT 1 FROM income_notifications
                WHERE user_id = %s
            )
        """, (self.alice.id,)) is False

    def test_notification_not_sent_if_recently_notified(self):
        # Simulate a recent notification
        self.db.run("""
            INSERT INTO income_notifications (user_id, notified_date)
            VALUES (%s, CURRENT_TIMESTAMP)
        """, (self.alice.id,))
        self.alice.check_income_goals()
        notifications = self.db.all("""
            SELECT * FROM income_notifications WHERE user_id = %s
        """, (self.alice.id,))
        assert len(notifications) == 1  # No new notification should be added

@pytest.fixture(autouse=True)
def setup(db):
    db.run("CREATE TEMPORARY TABLE transfers (recipient int, amount money, timestamp timestamp)")
    db.run("CREATE TEMPORARY TABLE income_notifications (user_id int, notified_date timestamp)")
