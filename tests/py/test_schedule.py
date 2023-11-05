from datetime import timedelta
from unittest.mock import patch

from pando.utils import utcnow

from liberapay.billing.payday import compute_next_payday_date
from liberapay.i18n.base import LOCALE_EN
from liberapay.models.participant import Participant
from liberapay.payin.common import update_payin_transfer
from liberapay.payin.cron import (
    execute_scheduled_payins,
    send_donation_reminder_notifications, send_upcoming_debit_notifications,
)
from liberapay.testing import EUR, USD
from liberapay.testing.emails import EmailHarness


class TestDonationRenewalScheduling(EmailHarness):

    def test_schedule_renewals(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        # pre-test
        new_schedule = alice.schedule_renewals()
        assert new_schedule == []
        # set up a donation
        alice.set_tip_to(bob, EUR('0.99'))
        new_schedule = alice.schedule_renewals()
        assert new_schedule == []
        # fund the donation
        alice_card = self.upsert_route(alice, 'stripe-card')
        self.make_payin_and_transfer(alice_card, bob, EUR('49.50'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': None,
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount is None
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == (next_payday + timedelta(weeks=50))
        assert new_schedule[0].automatic is False
        # check idempotency
        new_schedule2 = alice.schedule_renewals()
        assert len(new_schedule2) == 1
        assert new_schedule2[0].__dict__ == new_schedule[0].__dict__
        # modify the donation amount
        alice.set_tip_to(bob, EUR('1.98'))
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount is None
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == (next_payday + timedelta(weeks=25))
        assert new_schedule[0].automatic is False
        # enable automatic renewal for this donation
        alice.set_tip_to(bob, EUR('0.99'), renewal_mode=2)
        expected_transfers[0]['amount'] = EUR('49.50')
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('49.50')
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == (next_payday + timedelta(weeks=50, days=-1))
        assert new_schedule[0].automatic is True

    def test_schedule_renewals_handles_donations_to_teams(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        team = self.make_participant('team', kind='group')
        team.add_member(bob)
        team.add_member(carl)
        # set up a donation
        alice.set_tip_to(team, EUR('0.13'), renewal_mode=2)
        new_schedule = alice.schedule_renewals()
        assert new_schedule == []
        # fund the donation
        self.add_payment_account(bob, 'stripe')
        self.add_payment_account(carl, 'stripe')
        alice_card = self.upsert_route(alice, 'stripe-card')
        self.make_payin_and_transfer(alice_card, team, EUR('2.00'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': team.id,
                'tippee_username': 'team',
                'amount': EUR('2.00'),
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('2.00')
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == (next_payday + timedelta(weeks=15, days=-1))
        assert new_schedule[0].automatic is True
        # check idempotency
        new_schedule2 = alice.schedule_renewals()
        assert len(new_schedule2) == 1
        assert new_schedule2[0].__dict__ == new_schedule[0].__dict__

    def test_schedule_renewals_notifies_payer_of_changes(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('1.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('2.00'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': EUR('2.00'),
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('2.00')
        assert new_schedule[0].transfers == expected_transfers
        expected_renewal_date = next_payday + timedelta(weeks=2, days=-1)
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is True
        # Trigger the initial "upcoming charge" notification
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = current_date
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'alice <alice@liberapay.com>'
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €2.00'
        sp = self.db.one("SELECT * FROM scheduled_payins")
        assert sp.notifs_count == 1
        self.db.run("UPDATE scheduled_payins SET execution_date = %s",
                    (expected_renewal_date,))
        # Tweak the donation amount. The renewal shouldn't be pushed back and
        # the payer shouldn't be notified.
        alice.set_tip_to(bob, EUR('0.50'))
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('2.00')
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is True
        emails = self.get_emails()
        assert not emails
        # Lower the donation amount a lot more. This time the renewal should be
        # rescheduled and the payer should be notified of that change.
        alice.set_tip_to(bob, EUR('0.10'))
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('2.00')
        assert new_schedule[0].transfers == expected_transfers
        expected_renewal_date = next_payday + timedelta(weeks=20, days=-1)
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is True
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'alice <alice@liberapay.com>'
        assert emails[0]['subject'] == 'Liberapay donation renewal: your upcoming payment has changed'

    def test_schedule_renewals_properly_handles_partial_manual_renewals(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        alice.set_tip_to(bob, EUR('2.00'), renewal_mode=1)
        alice.set_tip_to(carl, EUR('2.00'), renewal_mode=1)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('10.00'))
        self.make_payin_and_transfer(alice_card, carl, EUR('12.00'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': None,
            },
            {
                'tippee_id': carl.id,
                'tippee_username': 'carl',
                'amount': None,
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount is None
        assert new_schedule[0].transfers == expected_transfers
        expected_renewal_date = next_payday + timedelta(weeks=5)
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is False
        # Trigger the initial "renewal reminder" notification
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = current_date
        """)
        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'alice <alice@liberapay.com>'
        assert emails[0]['subject'] == "It's time to renew your donations on Liberapay"
        sp = self.db.one("SELECT * FROM scheduled_payins")
        assert sp.notifs_count == 1
        self.db.run("UPDATE scheduled_payins SET execution_date = %s",
                    (expected_renewal_date,))
        # Renew one of the donations
        renewal_payin = self.make_payin_and_transfer(alice_card, bob, EUR('200.00'))[0]
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY execution_date, ctime")
        assert len(scheduled_payins) == 3
        assert scheduled_payins[0].amount is None
        assert scheduled_payins[0].automatic is False
        assert scheduled_payins[0].execution_date == expected_renewal_date
        assert scheduled_payins[0].payin == renewal_payin.id
        assert scheduled_payins[0].transfers == expected_transfers
        assert scheduled_payins[1].amount is None
        assert scheduled_payins[1].automatic is False
        expected_renewal_date = next_payday + timedelta(weeks=6)
        assert scheduled_payins[1].execution_date == expected_renewal_date
        assert scheduled_payins[1].payin is None
        assert scheduled_payins[1].transfers == [expected_transfers[1]]
        assert scheduled_payins[2].amount is None
        assert scheduled_payins[2].automatic is False
        expected_renewal_date = next_payday + timedelta(weeks=105)
        assert scheduled_payins[2].execution_date == expected_renewal_date
        assert scheduled_payins[2].payin is None
        assert scheduled_payins[2].transfers == [expected_transfers[0]]
        emails = self.get_emails()
        assert not emails

    def test_pending_manual_renewal_supersedes_scheduled_automatic_debit(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice.set_tip_to(carl, EUR('6.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('6.00'))
        self.make_payin_and_transfer(alice_card, carl, EUR('12.00'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': EUR('6.00'),
            },
            {
                'tippee_id': carl.id,
                'tippee_username': 'carl',
                'amount': EUR('12.00'),
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('18.00')
        assert new_schedule[0].transfers == expected_transfers
        expected_renewal_date = next_payday + timedelta(weeks=2, days=-1)
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is True
        # Trigger the initial "upcoming charge" notification
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = current_date
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'alice <alice@liberapay.com>'
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €18.00'
        sp = self.db.one("SELECT * FROM scheduled_payins")
        assert sp.notifs_count == 1
        self.db.run("UPDATE scheduled_payins SET execution_date = %s",
                    (expected_renewal_date,))
        # Initiate a manual renewal of one of the donations
        renewal_payin = self.make_payin_and_transfer(
            alice_card, bob, EUR('600.00'), status='pending',
        )[0]
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY execution_date, ctime")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('18.00')
        assert scheduled_payins[0].automatic is True
        assert scheduled_payins[0].execution_date == expected_renewal_date
        assert scheduled_payins[0].payin == renewal_payin.id
        # Call the renewal scheduler
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('12.00')
        assert new_schedule[0].automatic is True
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].transfers == [expected_transfers[1]]
        emails = self.get_emails()
        assert not emails

    def test_new_donation_isnt_scheduled_for_renewal_too_early(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('7.00'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': EUR('7.00'),
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('7.00')
        assert new_schedule[0].transfers == expected_transfers
        expected_renewal_date = next_payday + timedelta(weeks=2, days=-1)
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is True
        # Trigger the "upcoming charge" notification
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = current_date
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'alice <alice@liberapay.com>'
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €7.00'
        sp = self.db.one("SELECT * FROM scheduled_payins")
        assert sp.notifs_count == 1
        self.db.run("UPDATE scheduled_payins SET execution_date = %s",
                    (expected_renewal_date,))
        # Start another donation
        alice.set_tip_to(carl, EUR('1.00'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, carl, EUR('12.00'))
        old_schedule = new_schedule
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 2
        assert new_schedule[0] == old_schedule[0]
        assert new_schedule[1].amount == EUR('12.00')
        assert new_schedule[1].automatic is True
        expected_renewal_date = next_payday + timedelta(weeks=12, days=-1)
        assert new_schedule[1].execution_date == expected_renewal_date
        assert new_schedule[1].transfers == [
            {
                'tippee_id': carl.id,
                'tippee_username': 'carl',
                'amount': EUR('12.00'),
            }
        ]
        emails = self.get_emails()
        assert not emails

    def test_schedule_renewals_properly_handles_late_renewals(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('1.00'), renewal_mode=1)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('2.00'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': None,
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount is None
        assert new_schedule[0].transfers == expected_transfers
        expected_renewal_date = next_payday + timedelta(weeks=2)
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is False
        # Trigger the initial "upcoming charge" notification
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = current_date
        """)
        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'alice <alice@liberapay.com>'
        assert emails[0]['subject'] == "It's time to renew your donation to bob on Liberapay"
        sp = self.db.one("SELECT * FROM scheduled_payins")
        assert sp.notifs_count == 1
        # Renew the donation late
        fake_renewal_date = self.db.one("""
            UPDATE scheduled_payins
               SET execution_date = current_date - interval '1 day'
         RETURNING execution_date
        """)
        renewal_payin = self.make_payin_and_transfer(alice_card, bob, EUR('2.00'))[0]
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 2
        assert scheduled_payins[0].amount is None
        assert scheduled_payins[0].automatic is False
        assert scheduled_payins[0].execution_date == fake_renewal_date
        assert scheduled_payins[0].payin == renewal_payin.id
        assert scheduled_payins[0].transfers == expected_transfers
        assert scheduled_payins[1].amount is None
        assert scheduled_payins[1].automatic is False
        expected_renewal_date = next_payday + timedelta(weeks=4)
        assert scheduled_payins[1].execution_date == expected_renewal_date
        assert scheduled_payins[1].payin is None
        assert scheduled_payins[1].transfers == expected_transfers
        emails = self.get_emails()
        assert not emails

    def test_schedule_renewals_finds_partial_matches(self):
        """
        This test is designed to hit the `find_partial_match` function inside
        `Participant.schedule_renewals`.
        """
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        team = self.make_participant('team', kind='group', email='team@liberapay.com')
        team.add_member(bob)
        alice.set_tip_to(bob, EUR('1.00'), renewal_mode=2)
        alice.set_tip_to(team, EUR('1.50'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('2.00'))
        self.make_payin_and_transfer(alice_card, team, EUR('3.00'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': EUR('2.00'),
            },
            {
                'tippee_id': team.id,
                'tippee_username': 'team',
                'amount': EUR('3.00'),
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('5.00')
        assert new_schedule[0].transfers == expected_transfers
        expected_renewal_date = next_payday + timedelta(weeks=2, days=-1)
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is True
        # Trigger the initial "upcoming charge" notification
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = current_date - interval '6 days'
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'alice <alice@liberapay.com>'
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €5.00'
        sp = self.db.one("SELECT * FROM scheduled_payins WHERE payin IS NULL")
        assert sp.notifs_count == 1
        self.db.run("UPDATE scheduled_payins SET execution_date = %s",
                    (expected_renewal_date,))
        # Tweak the amount of the first donation. The renewal shouldn't be
        # pushed back and the payer shouldn't be notified.
        alice.set_tip_to(bob, EUR('0.50'))
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('5.00')
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is True
        emails = self.get_emails()
        assert not emails
        # Stop the second donation. The renewal should be rescheduled and the
        # payer should be notified of that change.
        alice.stop_tip_to(team)
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('2.00')
        assert new_schedule[0].transfers == [expected_transfers[0]]
        previous_renewal_date = expected_renewal_date
        expected_renewal_date = next_payday + timedelta(weeks=4, days=-1)
        assert new_schedule[0].execution_date == expected_renewal_date
        assert new_schedule[0].automatic is True
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'alice <alice@liberapay.com>'
        assert emails[0]['subject'] == 'Liberapay donation renewal: your upcoming payment has changed'
        expected_sentence = LOCALE_EN.format(
            "The payment of €5.00 scheduled for {old_date} has been replaced by "
            "a payment of €2.00 on {new_date}.",
            old_date=previous_renewal_date, new_date=expected_renewal_date
        )
        assert expected_sentence in emails[0]['text']

    def test_schedule_renewals_does_not_group_payments_years_apart(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        dana = self.make_participant('dana', email='dana@liberapay.com')
        alice.set_tip_to(bob, EUR('4.20'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('42.00'))
        alice.set_tip_to(carl, EUR('0.04'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, carl, EUR('24.00'))
        alice.set_tip_to(dana, EUR('0.75'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, dana, EUR('7.50'))
        scheduled_payins = alice.schedule_renewals()
        assert len(scheduled_payins) == 2
        assert scheduled_payins[0].amount == EUR('49.50')
        assert scheduled_payins[1].amount == EUR('24.00')

    def test_schedule_renewals_marks_paypal_payment_as_manual(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('5.99'), renewal_mode=2)
        alice_paypal = self.upsert_route(alice, 'paypal')
        self.make_payin_and_transfer(alice_paypal, bob, EUR('60.00'))
        scheduled_payins = alice.schedule_renewals()
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount is None
        assert scheduled_payins[0].automatic is False

    def test_schedule_renewals_handles_change_of_customized_renewal_to_automatic(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('0.99'))
        alice_card = self.upsert_route(alice, 'stripe-card')
        self.make_payin_and_transfer(alice_card, bob, EUR('49.50'))
        new_schedule = alice.schedule_renewals()
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': None,
            }
        ]
        assert len(new_schedule) == 1
        assert new_schedule[0].amount is None
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == (next_payday + timedelta(weeks=50))
        assert new_schedule[0].automatic is False
        # customize the renewal
        schedule = self.db.all("SELECT * FROM scheduled_payins WHERE payin IS NULL")
        assert len(schedule) == 1
        sp = schedule[0]
        r = self.client.GET("/alice/giving/schedule", auth_as=alice)
        assert r.code == 200
        r = self.client.GET(
            "/alice/giving/schedule?id=%i&action=modify" % sp.id,
            auth_as=alice
        )
        assert r.code == 200
        new_date = sp.execution_date - timedelta(days=14)
        r = self.client.PxST(
            "/alice/giving/schedule?id=%i&action=modify" % sp.id,
            {'new_date': new_date.isoformat()},
            auth_as=alice
        )
        assert r.code == 302
        sp = self.db.one("SELECT * FROM scheduled_payins WHERE id = %s", (sp.id,))
        assert sp.amount is None
        assert sp.transfers == expected_transfers
        assert sp.execution_date == new_date
        assert sp.customized is True
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount is None
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == new_date
        assert new_schedule[0].customized is True
        # enable automatic renewal for this donation
        alice.set_tip_to(bob, EUR('0.99'), renewal_mode=2)
        expected_transfers[0]['amount'] = EUR('49.50')
        new_schedule = alice.schedule_renewals()
        assert len(new_schedule) == 1
        assert new_schedule[0].amount == EUR('49.50')
        assert new_schedule[0].transfers == expected_transfers
        assert new_schedule[0].execution_date == new_date
        assert new_schedule[0].automatic is True

    def test_schedule_renewals_handles_currency_switch(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com', accepted_currencies=None)
        alice.set_tip_to(bob, EUR('1.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('37.00'))
        schedule = self.db.all("SELECT * FROM scheduled_payins WHERE payin IS NULL")
        next_payday = compute_next_payday_date()
        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': EUR('37.00').for_json(),
            }
        ]
        assert len(schedule) == 1
        assert schedule[0].amount == EUR('37.00')
        assert schedule[0].transfers == expected_transfers
        expected_renewal_date = next_payday + timedelta(weeks=37, days=-1)
        assert schedule[0].execution_date == expected_renewal_date
        assert schedule[0].automatic is True

        # Change the currency
        alice.set_tip_to(bob, USD('1.20'), renewal_mode=2)
        schedule = self.db.all("SELECT * FROM scheduled_payins WHERE payin IS NULL")
        assert len(schedule) == 1
        expected_transfers = [dict(expected_transfers[0], amount=USD('44.40').for_json())]
        assert schedule[0].amount == USD('44.40')
        assert schedule[0].transfers == expected_transfers
        assert schedule[0].execution_date == expected_renewal_date
        assert schedule[0].automatic is True

        # Customize the renewal
        sp_id = schedule[0].id
        r = self.client.GET("/alice/giving/schedule", auth_as=alice)
        assert r.code == 200
        r = self.client.GET(
            "/alice/giving/schedule?id=%i&action=modify" % sp_id,
            auth_as=alice
        )
        assert r.code == 200
        new_date = expected_renewal_date - timedelta(days=14)
        r = self.client.PxST(
            "/alice/giving/schedule?id=%i&action=modify" % sp_id,
            {
                'amount': '42.00', 'currency': 'USD',
                'new_date': new_date.isoformat(),
            },
            auth_as=alice
        )
        assert r.code == 302
        sp = self.db.one("SELECT * FROM scheduled_payins WHERE id = %s", (sp_id,))
        assert sp.amount == USD('42.00')
        assert sp.execution_date == new_date
        assert sp.customized is True
        schedule = alice.schedule_renewals()
        assert len(schedule) == 1
        assert schedule[0].amount == USD('42.00')
        assert schedule[0].execution_date == new_date
        assert schedule[0].customized is True

        # Change the currency again
        alice.set_tip_to(bob, EUR('1.00'), renewal_mode=2)
        schedule = self.db.all("SELECT * FROM scheduled_payins WHERE payin IS NULL")
        assert len(schedule) == 1
        expected_transfers = [dict(expected_transfers[0], amount=EUR('35.00').for_json())]
        assert schedule[0].amount == EUR('35.00')
        assert schedule[0].transfers == expected_transfers
        assert schedule[0].execution_date == new_date
        assert schedule[0].automatic is True
        assert schedule[0].customized is True

    def test_no_new_renewal_is_scheduled_when_there_is_a_pending_transfer(self):
        # Set up a funded manual donation
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('4.16'), renewal_mode=1)
        alice_sdd = self.upsert_route(alice, 'stripe-sdd')
        self.make_payin_and_transfer(alice_sdd, bob, EUR('8.32'))
        # At this point we should have a manual renewal scheduled in two weeks
        scheduled_payins = alice.schedule_renewals()
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount is None
        assert scheduled_payins[0].automatic is False
        # Initiate a new payment. It should "fulfill" the scheduled renewal.
        self.make_payin_and_transfer(alice_sdd, bob, EUR('77.00'), status='pending')
        scheduled_payins = alice.schedule_renewals()
        assert len(scheduled_payins) == 0
        # Turn on automatic renewals. No new renewal should be scheduled since
        # there is still a pending payment.
        r = self.client.PxST("/alice/giving/", {"auto_renewal": "yes"}, auth_as=alice)
        assert r.code == 302
        tip = alice.get_tip_to(bob)
        assert tip.renewal_mode == 2
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins WHERE payin IS NULL")
        assert len(scheduled_payins) == 0

    def test_newly_scheduled_automatic_payments_are_at_least_a_week_away(self):
        # Set up an automatic donation partially funded 4 weeks ago
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_sdd = self.upsert_route(alice, 'stripe-sdd')
        payin, pt = self.make_payin_and_transfer(alice_sdd, bob, EUR('2.00'), status='pending')
        self.db.run("UPDATE payin_transfers SET ctime = ctime - interval '4 weeks'")
        update_payin_transfer(self.db, pt.id, pt.remote_id, 'succeeded', None)
        # At this point we should have an automatic renewal scheduled one week from now
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('10.00')
        assert scheduled_payins[0].automatic is True
        payment_timedelta = scheduled_payins[0].execution_date - utcnow().date()
        assert payment_timedelta.days in (6, 7)
        assert not scheduled_payins[0].customized
        # Running the scheduler again shouldn't change anything.
        old_scheduled_payins = scheduled_payins
        alice.schedule_renewals()
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins")
        assert old_scheduled_payins == scheduled_payins

    def test_late_manual_payment_switched_to_automatic_is_scheduled_a_week_away(self):
        # Set up a manual donation
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=1)
        alice_sdd = self.upsert_route(alice, 'stripe-sdd')
        payin, pt = self.make_payin_and_transfer(alice_sdd, bob, EUR('2.00'), status='pending')
        self.db.run("UPDATE payin_transfers SET ctime = ctime - interval '3 weeks'")
        update_payin_transfer(self.db, pt.id, pt.remote_id, 'succeeded', None)
        # At this point we should have a manual renewal scheduled in the past
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount is None
        assert scheduled_payins[0].automatic is False
        payment_timedelta = scheduled_payins[0].execution_date - utcnow().date()
        assert payment_timedelta.days <= -6
        # Running the scheduler again shouldn't change anything.
        old_scheduled_payins = scheduled_payins
        alice.schedule_renewals()
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins")
        assert old_scheduled_payins == scheduled_payins
        # Turn on automatic renewals. The execution date should now be in the future.
        r = self.client.PxST("/alice/giving/", {"auto_renewal": "yes"}, auth_as=alice)
        assert r.code == 302
        tip = alice.get_tip_to(bob)
        assert tip.renewal_mode == 2
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins WHERE payin IS NULL")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('10.00')
        assert scheduled_payins[0].automatic is True
        payment_timedelta = scheduled_payins[0].execution_date - utcnow().date()
        assert payment_timedelta.days in (6, 7)
        assert not scheduled_payins[0].customized
        assert scheduled_payins[0].last_notif_ts is None
        assert scheduled_payins[0].notifs_count == 0
        # Running the scheduler again shouldn't change anything.
        old_scheduled_payins = scheduled_payins
        alice.schedule_renewals()
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins")
        assert old_scheduled_payins == scheduled_payins


class TestScheduledPayins(EmailHarness):

    def setUp(self):
        super().setUp()
        schedule_renewals = Participant.schedule_renewals
        self.sr_patch = patch.object(Participant, 'schedule_renewals', autospec=True)
        self.sr_mock = self.sr_patch.__enter__()
        self.sr_mock.side_effect = schedule_renewals

    def tearDown(self):
        self.sr_patch.__exit__(None, None, None)
        super().tearDown()

    def test_no_scheduled_payins(self):
        self.make_participant('alice')
        send_upcoming_debit_notifications()
        execute_scheduled_payins()
        send_donation_reminder_notifications()
        notifs = self.db.all("SELECT * FROM notifications")
        assert not notifs
        payins = self.db.all("SELECT * FROM payins")
        assert not payins

    def test_one_scheduled_payin(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_card = self.attach_stripe_payment_method(alice, 'pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('12.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('12.00')
        assert scheduled_payins[0].payin is None

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €12.00'

        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 0

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
        """)
        self.sr_mock.reset_mock()
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 2
        assert payins[0].payer == alice.id
        assert payins[0].amount == EUR('12.00')
        assert payins[0].off_session is False
        assert payins[0].status == 'succeeded'
        assert payins[1].payer == alice.id
        assert payins[1].amount == EUR('12.00')
        assert payins[1].off_session is True
        assert payins[1].status == 'succeeded'
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == "Your payment has succeeded"
        assert self.sr_mock.call_count == 1

        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY execution_date"
        )
        assert len(scheduled_payins) == 2
        assert scheduled_payins[0].payin == payins[1].id
        assert scheduled_payins[1].payin is None

    def test_multiple_scheduled_payins(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        dana = self.make_participant('dana', email='dana@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_card = self.attach_stripe_payment_method(alice, 'pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('12.00'))
        alice.set_tip_to(carl, EUR('0.01'), renewal_mode=1)
        self.make_payin_and_transfer(alice_card, carl, EUR('6.00'))
        alice.set_tip_to(dana, EUR('5.00'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, dana, EUR('25.00'))

        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY execution_date"
        )
        assert len(scheduled_payins) == 2
        assert scheduled_payins[0].amount == EUR('37.00')
        assert scheduled_payins[1].amount is None
        manual_payin = scheduled_payins[1]

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '7 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €37.00'

        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == "It's time to renew your donation to carl on Liberapay"
        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 0

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
        """)
        # Restore the correct date of the manual payin to avoid triggering a
        # `payment_schedule_modified` notification
        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = %(execution_date)s
             WHERE id = %(id)s
        """, manual_payin.__dict__)
        self.sr_mock.reset_mock()
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 4
        assert payins[0].payer == alice.id
        assert payins[0].amount == EUR('12.00')
        assert payins[0].off_session is False
        assert payins[0].status == 'succeeded'
        assert payins[1].payer == alice.id
        assert payins[1].amount == EUR('6.00')
        assert payins[1].off_session is False
        assert payins[1].status == 'succeeded'
        assert payins[2].payer == alice.id
        assert payins[2].amount == EUR('25.00')
        assert payins[2].off_session is False
        assert payins[2].status == 'succeeded'
        assert payins[3].payer == alice.id
        assert payins[3].amount == EUR('37.00')
        assert payins[3].off_session is True
        assert payins[3].status == 'succeeded'
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == "Your payment has succeeded"
        assert self.sr_mock.call_count == 1

    def test_early_manual_renewal_of_automatic_donations(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        dana = self.make_participant('dana', email='dana@liberapay.com')
        alice.set_tip_to(bob, EUR('4.10'), renewal_mode=2)
        alice_card = self.attach_stripe_payment_method(alice, 'pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('16.40'))
        alice.set_tip_to(carl, EUR('4.20'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, carl, EUR('16.80'))
        alice.set_tip_to(dana, EUR('4.30'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, dana, EUR('17.20'))

        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY execution_date"
        )
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('50.40')
        assert scheduled_payins[0].automatic is True
        renewal_date = scheduled_payins[0].execution_date

        manual_renewal_1 = self.make_payin_and_transfer(alice_card, bob, EUR('16.40'))[0]
        manual_renewal_2 = self.make_payin_and_transfers(alice_card, EUR('34.00'), [
            (carl, EUR('16.80'), {}),
            (dana, EUR('17.20'), {}),
        ])[0]
        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY mtime"
        )
        assert len(scheduled_payins) == 3
        assert scheduled_payins[0].payin == manual_renewal_1.id
        assert scheduled_payins[1].payin == manual_renewal_2.id
        assert scheduled_payins[2].amount == EUR('50.40')
        assert scheduled_payins[2].automatic is True
        assert scheduled_payins[2].execution_date > renewal_date

        send_donation_reminder_notifications()
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 0

    def test_canceled_and_impossible_transfers(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        dana = self.make_participant('dana', email='dana@liberapay.com')
        alice.set_tip_to(bob, EUR('4.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('16.00'))
        alice.set_tip_to(carl, EUR('0.02'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, carl, EUR('12.00'))
        alice.set_tip_to(dana, EUR('5.00'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, dana, EUR('20.00'))

        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY execution_date"
        )
        assert len(scheduled_payins) == 2
        assert scheduled_payins[0].amount == EUR('36.00')
        assert scheduled_payins[1].amount == EUR('12.00')

        bob.close()
        self.db.run("UPDATE participants SET is_suspended = true WHERE username = 'carl'")
        self.db.run("UPDATE tips SET renewal_mode = 1 WHERE tippee = %s", (dana.id,))

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debits totaling €28.00'

        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 0

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        self.sr_mock.reset_mock()
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 3
        emails = self.get_emails()
        assert len(emails) == 2
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: payment aborted'
        assert emails[1]['to'] == ['alice <alice@liberapay.com>']
        assert emails[1]['subject'] == 'Liberapay donation renewal: payment aborted'
        assert self.sr_mock.call_count == 0

    def test_canceled_scheduled_payin(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        alice.set_tip_to(bob, EUR('1.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('52.00'))
        alice.set_tip_to(carl, EUR('1.00'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, carl, EUR('52.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('104.00')
        assert scheduled_payins[0].automatic is True

        self.db.run("UPDATE tips SET renewal_mode = 0 WHERE tippee = %s", (bob.id,))
        self.db.run("UPDATE tips SET renewal_mode = 1 WHERE tippee = %s", (carl.id,))

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_upcoming_debit_notifications()
        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 0
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 0

    def test_scheduled_payin_suspended_payer(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('4.30'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('43.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('43.00')

        self.db.run("UPDATE participants SET is_suspended = true WHERE username = 'alice'")

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_donation_reminder_notifications()
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 0

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        self.sr_mock.reset_mock()
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 1
        assert payins[0].payer == alice.id
        assert payins[0].amount == EUR('43.00')
        assert payins[0].off_session is False
        emails = self.get_emails()
        assert len(emails) == 0
        assert self.sr_mock.call_count == 0

    def test_missing_route(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('30.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('30.00')

        alice_card.update_status('canceled')

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_donation_reminder_notifications()
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: no valid payment instrument'

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
        """)
        self.sr_mock.reset_mock()
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 1
        assert payins[0].payer == alice.id
        assert payins[0].amount == EUR('30.00')
        assert payins[0].off_session is False
        emails = self.get_emails()
        assert len(emails) == 0
        assert self.sr_mock.call_count == 0

    def test_scheduled_payin_requiring_authentication(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('4.30'), renewal_mode=2)
        alice_card = self.attach_stripe_payment_method(alice, 'pm_card_threeDSecureRequired')
        self.make_payin_and_transfer(alice_card, bob, EUR('43.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('43.00')

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '7 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €43.00'

        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 0

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        self.sr_mock.reset_mock()
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 2
        assert payins[1].payer == alice.id
        assert payins[1].amount == EUR('43.00')
        assert payins[1].off_session is True
        assert payins[1].status == 'awaiting_payer_action'
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: authentication required'
        payin_page_path = f'/alice/giving/pay/stripe/{payins[1].id}'
        assert payin_page_path in emails[0]['text']
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].payin == payins[1].id
        assert self.sr_mock.call_count == 0
        # Test the payin page, it should redirect to the 3DSecure page
        r = self.client.GET(payin_page_path, auth_as=alice, raise_immediately=False)
        assert r.code == 200
        assert r.headers[b'Refresh'].startswith(b'0;url=https://hooks.stripe.com/')

    def test_scheduled_automatic_payin_currency_unaccepted_before_reminder(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('1.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('52.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('52.00')

        r = self.client.PxST('/bob/edit/currencies', {
            'accepted_currencies:GBP': 'yes',
            'main_currency': 'GBP',
            'confirmed': 'true',
        }, auth_as=bob)
        assert r.code == 302, r.text
        emails = self.get_emails()
        assert len(emails) == 0

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '7 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 0, emails[0]['subject']
        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        self.sr_mock.reset_mock()
        execute_scheduled_payins()
        emails = self.get_emails()
        assert len(emails) == 0
        assert self.sr_mock.call_count == 0
        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == "It's time to renew your donation to bob on Liberapay"
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].notifs_count == 1

    def test_scheduled_automatic_payin_currency_unaccepted_after_reminder(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('5.60'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('56.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('56.00')

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '7 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €56.00'
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].notifs_count == 1

        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 0

        r = self.client.PxST('/bob/edit/currencies', {
            'accepted_currencies:USD': 'yes',
            'main_currency': 'USD',
            'confirmed': 'true',
        }, auth_as=bob)
        assert r.code == 302, r.text
        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
                 , ctime = (ctime - interval '12 hours')
        """)
        self.sr_mock.reset_mock()
        execute_scheduled_payins()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: manual action required'
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].payin is None
        assert scheduled_payins[0].notifs_count == 2
        assert self.sr_mock.call_count == 0

    def test_cancelling_a_scheduled_payin(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        dana = self.make_participant('dana', email='dana@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('12.00'))
        alice.set_tip_to(carl, EUR('0.01'), renewal_mode=1)
        self.make_payin_and_transfer(alice_card, carl, EUR('6.00'))
        alice.set_tip_to(dana, EUR('5.00'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, dana, EUR('25.00'))

        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY execution_date"
        )
        assert len(scheduled_payins) == 2
        assert scheduled_payins[0].amount == EUR('37.00')
        assert scheduled_payins[1].amount is None

        sp_id = scheduled_payins[0].id
        r = self.client.GET("/alice/giving/schedule", auth_as=alice)
        assert r.code == 200
        r = self.client.GET(
            "/alice/giving/schedule?id=%i&action=cancel" % sp_id, auth_as=alice
        )
        assert r.code == 200
        r = self.client.PxST(
            "/alice/giving/schedule?id=%i&action=cancel" % sp_id, auth_as=alice
        )
        assert r.code == 302

        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY execution_date"
        )
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount is None

        tips = self.db.all("""
            SELECT tipper, tippee, renewal_mode
              FROM current_tips
          ORDER BY ctime
        """, back_as=dict)
        assert tips == [
            {'tipper': alice.id, 'tippee': bob.id, 'renewal_mode': 0},
            {'tipper': alice.id, 'tippee': carl.id, 'renewal_mode': 1},
            {'tipper': alice.id, 'tippee': dana.id, 'renewal_mode': 0},
        ]

        emails = self.get_emails()
        assert len(emails) == 0

    def test_rescheduling(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        dana = self.make_participant('dana', email='dana@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('12.00'))
        alice.set_tip_to(carl, EUR('0.01'), renewal_mode=1)
        self.make_payin_and_transfer(alice_card, carl, EUR('6.00'))
        alice.set_tip_to(dana, EUR('5.00'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, dana, EUR('25.00'))

        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY execution_date"
        )
        assert len(scheduled_payins) == 2
        assert scheduled_payins[0].amount == EUR('37.00')
        assert scheduled_payins[1].amount is None

        sp_id = scheduled_payins[0].id
        r = self.client.GET("/alice/giving/schedule", auth_as=alice)
        assert r.code == 200
        r = self.client.GET(
            "/alice/giving/schedule?id=%i&action=modify" % sp_id,
            auth_as=alice
        )
        assert r.code == 200
        new_date = scheduled_payins[0].execution_date + timedelta(days=21)
        r = self.client.PxST(
            "/alice/giving/schedule?id=%i&action=modify" % sp_id,
            {'new_date': new_date.isoformat()}, auth_as=alice
        )
        assert r.code == 302

        sp = self.db.one(
            "SELECT * FROM scheduled_payins WHERE id = %s", (sp_id,)
        )
        assert sp.amount == EUR('37.00')
        assert sp.execution_date == new_date

        schedule = alice.schedule_renewals()
        assert len(schedule) == 2
        assert schedule[0].amount == EUR('37.00')
        assert schedule[0].execution_date == new_date

        emails = self.get_emails()
        assert len(emails) == 0

    def test_customizing_amount(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        dana = self.make_participant('dana', email='dana@liberapay.com')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_card = self.upsert_route(alice, 'stripe-card', address='pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('12.00'))
        alice.set_tip_to(carl, EUR('0.01'), renewal_mode=1)
        self.make_payin_and_transfer(alice_card, carl, EUR('6.00'))
        alice.set_tip_to(dana, EUR('5.00'), renewal_mode=2)
        self.make_payin_and_transfer(alice_card, dana, EUR('25.00'))

        scheduled_payins = self.db.all(
            "SELECT * FROM scheduled_payins ORDER BY execution_date"
        )
        assert len(scheduled_payins) == 2
        assert scheduled_payins[0].amount == EUR('37.00')
        assert scheduled_payins[1].amount is None

        sp_id = scheduled_payins[0].id
        renewal_date = scheduled_payins[0].execution_date
        r = self.client.GET("/alice/giving/schedule", auth_as=alice)
        assert r.code == 200
        r = self.client.GET(
            "/alice/giving/schedule?id=%i&action=modify" % sp_id,
            auth_as=alice
        )
        assert r.code == 200
        r = self.client.PxST(
            "/alice/giving/schedule?id=%i&action=modify" % sp_id,
            {'amount': '20.00', 'currency': 'EUR'}, auth_as=alice
        )
        assert r.code == 302

        # Check that a different currency is rejected
        r = self.client.POST(
            "/alice/giving/schedule?id=%i&action=modify" % sp_id,
            {'amount': '20.00', 'currency': 'USD'}, auth_as=alice,
            raise_immediately=False,
        )
        assert r.code == 400, r.text
        assert " expected currency (EUR)." in r.text

        expected_transfers = [
            {
                'tippee_id': bob.id,
                'tippee_username': 'bob',
                'amount': {
                    'amount': '6.49',
                    'currency': 'EUR',
                },
            },
            {
                'tippee_id': dana.id,
                'tippee_username': 'dana',
                'amount': {
                    'amount': '13.51',
                    'currency': 'EUR',
                },
            },
        ]
        sp = self.db.one("SELECT * FROM scheduled_payins WHERE id = %s", (sp_id,))
        assert sp.amount == EUR('20.00')
        assert sp.transfers == expected_transfers
        assert sp.execution_date == renewal_date

        schedule = alice.schedule_renewals()
        assert len(schedule) == 2
        sp = self.db.one("SELECT * FROM scheduled_payins WHERE id = %s", (sp_id,))
        assert sp.amount == EUR('20.00')
        assert sp.transfers == expected_transfers
        assert sp.execution_date == renewal_date

        emails = self.get_emails()
        assert len(emails) == 0

    def test_reminders_to_renew_a_manual_donation(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        alice.set_tip_to(bob, EUR('52.00'), period='yearly')
        alice_card = self.upsert_route(alice, 'stripe-card')
        self.make_payin_and_transfer(alice_card, bob, EUR('2.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount is None
        assert scheduled_payins[0].payin is None

        # A week later, a first reminder should be sent
        self.db.run("""
            UPDATE payins
               SET ctime = ctime - interval '8 days';
            UPDATE payin_transfers
               SET ctime = ctime - interval '8 days';
            UPDATE tips
               SET paid_in_advance = ('1.00', 'EUR')::currency_amount;
            UPDATE scheduled_payins
               SET execution_date = current_date + interval '5 days'
                 , ctime = ctime - interval '8 days';
        """)
        send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == "It's time to renew your donation to bob on Liberapay"

        # Several weeks later, a second reminder should be sent
        self.db.run("""
            UPDATE payins
               SET ctime = ctime - interval '5 weeks';
            UPDATE payin_transfers
               SET ctime = ctime - interval '5 weeks';
            UPDATE notifications
               SET ts = ts - interval '5 weeks';
            UPDATE scheduled_payins
               SET last_notif_ts = last_notif_ts - interval '5 weeks';
        """)
        with patch.object(self.db.Tip, 'compute_renewal_due_date') as compute_renewal_due_date:
            compute_renewal_due_date.return_value = utcnow().date() - timedelta(weeks=5)
            send_donation_reminder_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == "It's past time to renew your donation to bob on Liberapay"

        # Of course, there shouldn't be any new payin or scheduled payin
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins")
        assert len(scheduled_payins) == 1
        payins = self.db.all("SELECT * FROM payins")
        assert len(payins) == 1
