from datetime import datetime, timedelta
import json
from unittest.mock import patch

from psycopg2.extras import execute_values

from liberapay.cron import Daily, Weekly
from liberapay.i18n.currencies import fetch_currency_exchange_rates
from liberapay.models.participant import send_account_disabled_notifications
from liberapay.testing.emails import EmailHarness
from liberapay.models.participant import \
    generate_profile_description_missing_notifications
from liberapay.billing.payday import Payday
from liberapay.testing import EUR


utcnow = datetime.utcnow


class TestCronJobs(EmailHarness):

    @patch('liberapay.cron.sleep')
    @patch('liberapay.cron.datetime', autospec=True)
    @patch('liberapay.cron.break_after_call', return_value=True)
    def test_cron_jobs_with_empty_db(self, bac, datetime, sleep):
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
                job.thread.join(10)
                assert mock_func.call_count == 1

    @patch('liberapay.cron.sleep')
    @patch('liberapay.cron.datetime', autospec=True)
    @patch('liberapay.cron.break_before_call', return_value=True)
    def test_weekly_and_daily_cron_jobs_at_the_wrong_time(self, bbc, datetime, sleep):
        def forward_time(seconds):
            datetime.utcnow.return_value += timedelta(seconds=seconds)

        now = utcnow()
        sleep.side_effect = forward_time
        for job in self.website.cron.jobs:
            print(job)
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
                    job.thread.join(10)
                    assert sleep.call_count == 1
                    # Not yet time
                    datetime.utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=0, second=0) +
                        days_delta
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 2
                    # Too late
                    datetime.utcnow.return_value = (
                        now.replace(hour=job.period.hour, minute=20, second=0) +
                        days_delta
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 4
                elif isinstance(job.period, Daily):
                    # Not yet time
                    datetime.utcnow.return_value = utcnow().replace(
                        hour=job.period.hour, minute=0, second=0
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 1
                    # Too late
                    datetime.utcnow.return_value = utcnow().replace(
                        hour=job.period.hour, minute=10, second=0
                    )
                    job.start()
                    job.thread.join(10)
                    assert sleep.call_count == 2
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

    def test_first_payday_notifies_participants_without_description(self):
        # alex: no description, doesn't receive payments. No email
        alex = self.make_participant('alex', email='alex@example.org')
        # bob: no description, receives payments. Email
        bob = self.make_participant('bob', email='bob@example.org')
        # charles: has description, doesn't receives payments. No email
        charles = self.make_participant('charles', email='charles@example.org')
        # dave: has description, receives payments. No email
        dave = self.make_participant('dave', email='dave@example.org')

        # add payment accounts for bob and dave and cards for alex and charles
        self.add_payment_account(bob, 'stripe', country='FR', default_currency='EUR')
        self.add_payment_account(dave, 'stripe', country='FR', default_currency='EUR')
        alex_card = self.upsert_route(alex, 'stripe-card')
        charles_card = self.upsert_route(charles, 'stripe-card')

        # set descriptions
        charles.upsert_statement('en', "Profile statement.")
        dave.upsert_statement('en', "Profile statement.")

        # send payments
        alex.set_tip_to(bob, EUR('4.50'))
        charles.set_tip_to(dave, EUR('4.50'))
        self.make_payin_and_transfer(alex_card, bob, EUR('4.50'))
        self.make_payin_and_transfer(charles_card, dave, EUR('4.50'))

        # run first paydays
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = execution_date - interval '2 weeks'
        """)
        Payday.start().run()
        generate_profile_description_missing_notifications()
        emails = self.get_emails()

        # 2 income notifications (bob, dave)
        # 2 donation renewal reminders (alex, charles)
        # 1 missing description reminder (bob)
        assert len(emails) == 5

        # get emails about updating profile only
        profile_desc_emails = emails.copy()
        for email in emails:
            if "missing a profile description" not in email['subject']:
                profile_desc_emails.remove(email)
        emails = profile_desc_emails

        # should be just one (bob)
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'bob <%s>' % bob.email
        assert 'missing a profile description' in emails[0]['subject']

        # ## should only send missing description email after first payday
        # send more payments
        alex.set_tip_to(bob, EUR('4.50'))
        charles.set_tip_to(dave, EUR('4.50'))
        self.make_payin_and_transfer(alex_card, bob, EUR('4.50'))
        self.make_payin_and_transfer(charles_card, dave, EUR('4.50'))

        # run 2nd payday
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")
        Payday.start().run()
        generate_profile_description_missing_notifications()
        emails = self.get_emails()

        # 2 income notifications (bob, dave)
        assert len(emails) == 2

        # get emails about updating profile only
        profile_desc_emails = emails.copy()
        for email in emails:
            if "missing a profile description" not in email['subject']:
                profile_desc_emails.remove(email)
        emails = profile_desc_emails

        # should be none, bob already got an email about updating profile
        assert emails == []

        # ## team members should get these emails too
        # create team user
        ethan = self.make_participant('ethan', email='ethan@example.org')
        self.add_payment_account(ethan, 'stripe', country='FR', default_currency='EUR')

        # send more payments
        team = self.make_participant('team', kind='group', email='team@example.com')
        charles.set_tip_to(team, EUR('0.25'))
        team.add_member(ethan)
        team.set_take_for(ethan, EUR('0.23'), team)
        self.make_payin_and_transfer(charles_card, team, EUR('0.50'))

        # run 3rd payday
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")
        Payday.start().run()
        generate_profile_description_missing_notifications()
        emails = self.get_emails()

        # 1 income notification (ethan)
        # 1 missing description reminder (ethan)
        assert len(emails) == 2
        assert 'missing a profile description' in emails[1]['subject']
        assert '0.23' in emails[0]['subject']
        assert emails[0]['to'][0] == 'ethan <%s>' % ethan.email
        ethan.leave_team(team)

        # ## fast forward 6 months,
        self.db.run("UPDATE notifications SET ts = ts - interval '181 days'")
        self.db.run("UPDATE transfers SET timestamp = timestamp - interval '181 days'")
        generate_profile_description_missing_notifications()
        emails = self.get_emails()
        # no one should get an email about creating a description
        # because no one received payments in last 6 months
        assert emails == []

        # send bob a tip,
        # bob should get a fresh missing description email but ethan shouldn't
        charles.set_tip_to(bob, EUR('4.50'))
        self.make_payin_and_transfer(charles_card, bob, EUR('4.50'))
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")
        Payday.start().run()
        generate_profile_description_missing_notifications()
        emails = self.get_emails()
        assert len(emails) == 2
        assert 'missing a profile description' in emails[1]['subject']
        assert '4.50' in emails[0]['subject']
        assert emails[0]['to'][0] == 'bob <%s>' % bob.email
