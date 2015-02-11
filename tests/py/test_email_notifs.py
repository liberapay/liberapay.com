import mock

from gratipay.models.participant import Participant
from gratipay.models.account_elsewhere import AccountElsewhere
from gratipay.testing import Harness
from gratipay.testing.emails import get_last_email, wait_for_email_thread

class TestTransactionalEmails(Harness):

    def setUp(self):
        self.bob = self.make_participant('bob', claimed_time='now', email_address='bob@gmail.com')
        self.dan = self.make_participant('dan', claimed_time='now', email_address='dan@gmail.com')
        self.alice = self.make_participant('alice', claimed_time='now', email_address='alice@gmail.com')

        self.mailer_patcher = mock.patch.object(Participant._mailer.messages, 'send')
        self.test_mailer = self.mailer_patcher.start()
        self.addCleanup(self.mailer_patcher.stop)

    def test_opt_in_sends_notifications_to_patrons(self):
        carl_twitter = self.make_elsewhere('twitter', 1, 'carl')
        roy = self.make_participant('roy', claimed_time='now', email_address='roy@gmail.com', notify_on_opt_in=False)

        self.bob.set_tip_to(carl_twitter.participant.username, '100')
        self.dan.set_tip_to(carl_twitter.participant.username, '100')
        roy.set_tip_to(carl_twitter.participant.username, '100') # Roy will NOT receive an email.

        AccountElsewhere.from_user_name('twitter', 'carl').opt_in('carl')

        wait_for_email_thread()

        assert self.test_mailer.call_count == 2 # Emails should only be sent to bob and dan
        last_email = get_last_email(self.test_mailer)
        assert last_email['to'] == 'dan@gmail.com'
        expected = "You had pledged to carl. They've just joined Gratipay!"
        assert expected in last_email['message_text']

    def test_take_over_sends_notifications_to_patrons(self):
        dan_twitter = self.make_elsewhere('twitter', 1, 'dan')

        self.alice.set_tip_to(self.dan, '100') # Alice shouldn't receive an email.
        self.bob.set_tip_to(dan_twitter.participant.username, '100') # Bob should receive an email.

        self.dan.take_over(dan_twitter, have_confirmation=True)

        wait_for_email_thread()

        assert self.test_mailer.call_count == 1
        last_email = get_last_email(self.test_mailer)
        assert last_email['to'] == 'bob@gmail.com'
        expected = "You had pledged to dan. They've just joined Gratipay!"
        assert expected in last_email['message_text']
