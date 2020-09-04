from unittest import mock

from liberapay.models.participant import Participant
from liberapay.testing import Harness


class EmailHarness(Harness):

    def setUp(self):
        super().setUp()
        self.mailer_patcher = mock.patch.object(self.client.website.mailer, 'send')
        self.mailer = self.mailer_patcher.start()
        self.mailer.return_value = 1
        self.addCleanup(self.mailer_patcher.stop)
        sleep_patcher = mock.patch('liberapay.models.participant.sleep')
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)

    def get_last_email(self):
        return self.mailer.call_args[1]

    def get_emails(self):
        Participant.dequeue_emails()
        emails = [a[1] for a in self.mailer.call_args_list]
        self.mailer.reset_mock()
        return emails
