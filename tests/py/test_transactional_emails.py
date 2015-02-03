import mock
import threading

from gratipay.models.participant import Participant
from gratipay.models.account_elsewhere import AccountElsewhere
from gratipay.testing import Harness
from gratipay.testing.emails import get_last_email

class TestTransactionalEmails(Harness):

    @mock.patch.object(Participant._mailer.messages, 'send')
    def test_opt_in_sends_notifications_to_patrons(self, mailer):
        alice = self.make_elsewhere('twitter', 1, 'alice')
        bob = self.make_participant('bob', claimed_time='now', email_address='bob@gmail.com')
        dan = self.make_participant('dan', claimed_time='now', email_address='dan@gmail.com')
        self.make_participant('roy', claimed_time='now', email_address='roy@gmail.com', notify_on_opt_in=False)
        bob.set_tip_to(alice.participant.username, '100')
        dan.set_tip_to(alice.participant.username, '100')
        alice = AccountElsewhere.from_user_name('twitter', 'alice')
        alice.opt_in('alice')

        # Emails are processed in a thread, wait for it to complete
        email_thread = filter(lambda x: x.name == 'email', threading.enumerate())
        if email_thread:
            email_thread[0].join()

        assert mailer.call_count == 2
        last_email = get_last_email(mailer)
        assert last_email['to'] == 'dan@gmail.com'
        expected = "You had pledged to alice. They've just joined Gratipay!"
        assert expected in last_email['message_text']
