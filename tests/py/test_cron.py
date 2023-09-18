from datetime import timedelta
import json
from unittest.mock import patch

from pando.utils import utcnow

from liberapay.constants import PAYIN_AMOUNTS
from liberapay.cron import Daily, Weekly
from liberapay.i18n.currencies import fetch_currency_exchange_rates
from liberapay.models.participant import (
    generate_profile_description_missing_notifications,
    send_account_disabled_notifications,
)
from liberapay.testing import EUR
from liberapay.testing.emails import EmailHarness


class TestCronJobs(EmailHarness):

    @patch('liberapay.cron.sleep')
    @patch('liberapay.cron.utcnow', autospec=True)
    @patch('liberapay.cron.break_after_call', return_value=True)
    def test_cron_jobs_with_empty_db(self, bac, cron_utcnow, sleep):
        now = utcnow()
        self.website.cron.has_lock = True
        for job in self.website.cron.jobs:
            print(job)
            real_func = job.func
            with patch.object(job, 'func', autospec=True) as mock_func:
                if isinstance(job.period, Weekly):
                    cron_utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=10, second=0) +
                        timedelta(days=(job.period.weekday - now.isoweekday()) % 7)
                    )
                elif isinstance(job.period, Daily):
                    cron_utcnow.return_value = now.replace(
                        hour=job.period.hour, minute=5, second=0
                    )
                else:
                    cron_utcnow.return_value = now
                if isinstance(job.period, Weekly) or real_func is fetch_currency_exchange_rates:
                    mock_func.side_effect = None
                else:
                    mock_func.side_effect = real_func
                job.start()
                job.thread.join(10)
                assert mock_func.call_count == 1

    @patch('liberapay.cron.sleep')
    @patch('liberapay.cron.utcnow', autospec=True)
    @patch('liberapay.cron.break_before_call', return_value=True)
    def test_weekly_and_daily_cron_jobs_at_the_wrong_time(self, bbc, cron_utcnow, sleep):
        now = utcnow()
        for job in self.website.cron.jobs:
            print(job)
            with patch.object(job, 'func', autospec=True) as mock_func:
                mock_func.return_value = None
                if isinstance(job.period, Weekly):
                    days_delta = timedelta(days=(job.period.weekday - now.isoweekday()) % 7)
                    # Wrong day
                    cron_utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=10, second=0) +
                        days_delta + timedelta(days=1)
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 1
                    # Not yet time
                    cron_utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=0, second=0) +
                        days_delta
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 2
                    # Late
                    cron_utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=20, second=0) +
                        days_delta
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 2
                elif isinstance(job.period, Daily):
                    # Not yet time
                    cron_utcnow.return_value = utcnow().replace(
                        hour=job.period.hour, minute=0, second=0
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 1
                    # Late
                    cron_utcnow.return_value = utcnow().replace(
                        hour=job.period.hour, minute=10, second=0
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 1
            sleep.reset_mock()

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
        assert PAYIN_AMOUNTS['paypal']['min_acceptable']['HUF']
        assert 'HUF' in PAYIN_AMOUNTS['paypal']['min_acceptable']
        currency_exchange_rates = self.client.website.currency_exchange_rates.copy()
        try:
            with self.allow_changes_to('currency_exchange_rates'), self.db.get_cursor() as cursor:
                fetch_currency_exchange_rates(cursor)
                cursor.connection.rollback()
        finally:
            self.client.website.currency_exchange_rates = currency_exchange_rates
        assert 'HUF' not in PAYIN_AMOUNTS['paypal']['min_acceptable']

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
            '/admin/users', data={'p_id': str(fraudster.id), 'mark_as': 'fraud'},
            auth_as=admin,
        )
        assert r.code == 200
        assert json.loads(r.text) == {"msg": "Done, 1 attribute has been updated."}
        r = self.client.PxST(
            '/admin/users', data={'p_id': str(spammer.id), 'mark_as': 'spam'},
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

    def test_profile_description_missing_notification(self):
        # alex: no description, doesn't receive payments, shouldn't be notified
        alex = self.make_participant('alex', email='alex@example.org')
        # bob: no description, receives payments, should be notified
        bob = self.make_participant('bob', email='bob@example.org')
        # charles: has description, doesn't receives payments, shouldn't be notified
        charles = self.make_participant('charles', email='charles@example.org')
        # dave: has description, receives payments, shouldn't be notified
        dave = self.make_participant('dave', email='dave@example.org')
        # emma: no description, declines donations, shouldn't be notified
        emma = self.make_participant('emma', email='emma@example.org', goal=EUR(-1))

        # add payment accounts for bob and dave and cards for alex and charles
        self.add_payment_account(bob, 'stripe')
        self.add_payment_account(dave, 'stripe')
        alex_card = self.upsert_route(alex, 'stripe-card')
        charles_card = self.upsert_route(charles, 'stripe-card')

        # add profile descriptions
        charles.upsert_statement('en', "Profile statement.")
        dave.upsert_statement('en', "Profile statement.")

        # send payments
        alex.set_tip_to(bob, EUR('4.50'))
        charles.set_tip_to(dave, EUR('4.50'))
        self.make_payin_and_transfer(alex_card, bob, EUR('4.50'))
        self.make_payin_and_transfer(charles_card, dave, EUR('4.50'))

        # set up a pledge to emma
        charles.set_tip_to(emma, EUR('4.50'))
        assert emma.receiving == EUR('4.50')

        # run the cron job
        generate_profile_description_missing_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'bob <%s>' % bob.email
        assert emails[0]['subject'] == "Your Liberapay profile is incomplete"

        # run the cron job again, there shouldn't be any new notification
        generate_profile_description_missing_notifications()
        emails = self.get_emails()
        assert not emails

        # users who receive through teams should also be notified
        ethan = self.make_participant('ethan', email='ethan@example.org')
        self.add_payment_account(ethan, 'stripe')
        team = self.make_participant('team', kind='group', email='team@example.com')
        charles.set_tip_to(team, EUR('0.25'))
        team.add_member(ethan)
        team.set_take_for(ethan, EUR('0.23'), team)
        self.make_payin_and_transfer(charles_card, team, EUR('5.00'))
        generate_profile_description_missing_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'ethan <%s>' % ethan.email
        assert emails[0]['subject'] == "Your Liberapay profile is incomplete"

        # run the cron job again, there shouldn't be any new notification
        generate_profile_description_missing_notifications()
        emails = self.get_emails()
        assert not emails
