from psycopg2.extras import execute_values

from liberapay.cron import Weekly
from liberapay.i18n.currencies import fetch_currency_exchange_rates
from liberapay.testing import Harness


class TestCronJobs(Harness):

    def test_cron_jobs_with_empty_db(self):
        for period, func, exclusive in self.website.cron.jobs:
            if not isinstance(period, Weekly) and func is not fetch_currency_exchange_rates:
                func()

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
