from datetime import datetime, timedelta
import json
from unittest.mock import patch

from psycopg2.extras import execute_values

from liberapay.cron import Daily, Weekly
from liberapay.i18n.currencies import fetch_currency_exchange_rates
from liberapay.models.participant import send_account_disabled_notifications
from liberapay.testing import fake_sleep
from liberapay.testing.emails import EmailHarness


utcnow = datetime.utcnow


class TestCronJobs(EmailHarness):

    @fake_sleep(target='liberapay.cron.sleep', raise_after=0)
    @patch('liberapay.cron.datetime', autospec=True)
    def test_cron_jobs_with_empty_db(self, datetime):
        now = utcnow()
        for job in self.website.cron.jobs:
            real_func = job.func
            with patch.object(job, 'func', autospec=True) as mock_func:
                if isinstance(job.period, Weekly):
                    datetime.utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=10, second=0) +
                        timedelta(days=(job.period.weekday - now.isoweekday()) % 7)
                    )
                elif isinstance(job.period, Daily):
                    datetime.utcnow.return_value = now.replace(
                        hour=job.period.hour, minute=5, second=0
                    )
                if isinstance(job.period, Weekly) or real_func is fetch_currency_exchange_rates:
                    mock_func.side_effect = None
                else:
                    mock_func.side_effect = real_func
                job.start()
                job.thread.join()
                assert mock_func.call_count == 1

    @fake_sleep(target='liberapay.cron.sleep', raise_after=0)
    @patch('liberapay.cron.datetime', autospec=True)
    def test_weekly_and_daily_cron_jobs_at_the_wrong_time(self, datetime):
        now = utcnow()
        for job in self.website.cron.jobs:
            with patch.object(job, 'func', autospec=True) as mock_func:
                mock_func.return_value = None
                if isinstance(job.period, Weekly):
                    days_delta = timedelta(days=(job.period.weekday - now.isoweekday()) % 7)
                    # Wrong day
                    datetime.utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=10, second=0) +
                        days_delta + timedelta(days=1)
                    )
                    job.start()
                    job.thread.join()
                    assert mock_func.call_count == 0
                    # Not yet time
                    datetime.utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=0, second=0) +
                        days_delta
                    )
                    job.start()
                    job.thread.join()
                    assert mock_func.call_count == 0
                    # Too late
                    datetime.utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=20, second=0) +
                        days_delta
                    )
                    job.start()
                    job.thread.join()
                    assert mock_func.call_count == 0
                elif isinstance(job.period, Daily):
                    # Not yet time
                    datetime.utcnow.return_value = utcnow().replace(
                        hour=job.period.hour, minute=0, second=0
                    )
                    job.start()
                    job.thread.join()
                    assert mock_func.call_count == 0
                    # Too late
                    datetime.utcnow.return_value = utcnow().replace(
                        hour=job.period.hour, minute=10, second=0
                    )
                    job.start()
                    job.thread.join()
                    assert mock_func.call_count == 0

    def test_disabled_job_is_not_run(self):
        job = self.website.cron.jobs[0]
        period = job.period
        job.period = 0
        with patch.object(job, 'func', autospec=True) as mock_func:
            try:
                r = job.start()
                assert r is None
                assert mock_func.call_count == 0
            finally:
                job.period = period

    def test_fetch_currency_exchange_rates(self):
        fake_rates = self.db.all("SELECT * FROM currency_exchange_rates")
        fetch_currency_exchange_rates()
        with self.db.get_cursor() as cursor:
            cursor.run("DELETE FROM currency_exchange_rates")
            execute_values(cursor, """
                INSERT INTO currency_exchange_rates
                            (source_currency, target_currency, rate)
                     VALUES %s
            """, fake_rates)

    def test_send_account_disabled_notifications(self):
        admin = self.make_participant('admin', privileges=1)
        fraudster = self.make_participant('fraudster', email='fraudster@example.com')
        spammer = self.make_participant('spammer', email='spammer@example.com')
        spammer.upsert_statement('en', "spammy summary", 'summary')
        spammer.upsert_statement('en', "spammy profile", 'profile')
        # First check, there aren't any notifications to send
        send_account_disabled_notifications()
        emails = self.get_emails()
        assert not emails
        # Flag the accounts
        r = self.client.PxST(
            '/admin/users', data={'p_id': str(fraudster.id), 'is_suspended': 'yes'},
            auth_as=admin,
        )
        assert r.code == 200
        assert json.loads(r.text) == {"msg": "Done, 1 attribute has been updated."}
        r = self.client.PxST(
            '/admin/users', data={'p_id': str(spammer.id), 'is_spam': 'yes'},
            auth_as=admin,
        )
        assert r.code == 200
        assert json.loads(r.text) == {"msg": "Done, 1 attribute has been updated."}
        # Check that the notifications aren't sent yet
        send_account_disabled_notifications()
        emails = self.get_emails()
        assert not emails
        # Check that the spam profile is hidden
        r = self.client.GET('/spammer/', raise_immediately=False)
        assert r.code == 200
        assert 'spammy' not in r.text, r.text
        # Make it look like the accounts were flagged 24 hours ago
        self.db.run("UPDATE events SET ts = ts - interval '24 hours'")
        # Check that the notifications are sent
        send_account_disabled_notifications()
        emails = self.get_emails()
        assert len(emails) == 2
        assert emails[0]['to'] == ['fraudster <fraudster@example.com>']
        assert emails[0]['subject'] == "Your Liberapay account has been disabled"
        assert 'fraud' in emails[0]['text']
        assert emails[1]['to'] == ['spammer <spammer@example.com>']
        assert emails[1]['subject'] == "Your Liberapay account has been disabled"
        assert 'spam' in emails[1]['text']
        # Check that the notifications aren't sent again
        send_account_disabled_notifications()
        emails = self.get_emails()
        assert not emails
