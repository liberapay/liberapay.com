from liberapay.models.participant import Participant
from liberapay.testing.emails import EmailHarness


class TestTransactionalEmails(EmailHarness):

    def setUp(self):
        EmailHarness.setUp(self)
        self.bob = self.make_participant('bob', email='bob@example.com')
        self.dan = self.make_participant('dan', email='dan@example.com')
        self.alice = self.make_participant('alice', email='alice@example.com')

    def test_take_over_sends_notifications_to_patrons(self):
        dan_twitter = self.make_elsewhere('twitter', 1, 'dan')

        self.alice.set_tip_to(self.dan, '100') # Alice shouldn't receive an email.
        self.bob.set_tip_to(dan_twitter, '100') # Bob should receive an email.

        self.dan.take_over(dan_twitter, have_confirmation=True)

        Participant.dequeue_emails()
        assert self.mailer.call_count == 1
        last_email = self.get_last_email()
        assert last_email['to'][0]['email'] == 'bob@example.com'
        assert "to dan" in last_email['text']
        assert "Change your email settings" in last_email['text']
