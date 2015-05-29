from liberapay.models.participant import Participant
from liberapay.testing.emails import EmailHarness


class TestTransactionalEmails(EmailHarness):

    def setUp(self):
        EmailHarness.setUp(self)
        self.bob = self.make_participant('bob', email_address='bob@example.com')
        self.dan = self.make_participant('dan', email_address='dan@example.com')
        self.alice = self.make_participant('alice', email_address='alice@example.com')

    def test_opt_in_sends_notifications_to_patrons(self):
        carl_twitter = self.make_elsewhere('twitter', 1, 'carl')
        roy = self.make_participant('roy', email_address='roy@example.com')
        self.client.POST( '/roy/emails/notifications.json'
                        , data={'toggle': 'notify_on_opt_in'}
                        , auth_as='roy'
                         )

        self.bob.set_tip_to(carl_twitter, '100')
        self.dan.set_tip_to(carl_twitter, '100')
        roy.set_tip_to(carl_twitter, '100') # Roy will NOT receive an email.

        carl_twitter.opt_in('carl')

        Participant.dequeue_emails()
        assert self.mailer.call_count == 2 # Emails should only be sent to bob and dan
        last_email = self.get_last_email()
        assert last_email['to'][0]['email'] == 'dan@example.com'
        expected = "to carl"
        assert expected in last_email['text']

    def test_take_over_sends_notifications_to_patrons(self):
        dan_twitter = self.make_elsewhere('twitter', 1, 'dan')

        self.alice.set_tip_to(self.dan, '100') # Alice shouldn't receive an email.
        self.bob.set_tip_to(dan_twitter, '100') # Bob should receive an email.

        self.dan.take_over(dan_twitter, have_confirmation=True)

        Participant.dequeue_emails()
        assert self.mailer.call_count == 1
        last_email = self.get_last_email()
        assert last_email['to'][0]['email'] == 'bob@example.com'
        expected = "to dan"
        assert expected in last_email['text']

    def test_opt_in_notification_includes_unsubscribe(self):
        carl_twitter = self.make_elsewhere('twitter', 1, 'carl')
        roy = self.make_participant('roy', email_address='roy@example.com', notify_on_opt_in=1)
        roy.set_tip_to(carl_twitter, '100')

        carl_twitter.opt_in('carl')

        Participant.dequeue_emails()
        assert "To stop receiving" in self.get_last_email()['text']
