from datetime import datetime, timedelta
from unittest.mock import patch

from psycopg2.extras import execute_values

from liberapay.cron import Daily, Weekly
from liberapay.i18n.currencies import fetch_currency_exchange_rates
from liberapay.testing import fake_sleep, Harness


utcnow = datetime.utcnow


class TestCronJobs(Harness):

    @fake_sleep(target='liberapay.cron.sleep', raise_after=0)
    @patch('liberapay.cron.datetime', autospec=True)
    def test_cron_jobs_with_empty_db(self, datetime):
        now = utcnow()
        for job in self.website.cron.jobs:
            print(job)
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
                if isinstance(job.period, Weekly) or job.func is fetch_currency_exchange_rates:
                    mock_func.return_value = None
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
