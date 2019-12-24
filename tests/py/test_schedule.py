from liberapay.payin.cron import (
    execute_scheduled_payins, send_upcoming_debit_notifications,
)
from liberapay.testing import EUR
from liberapay.testing.emails import EmailHarness


class TestScheduledPayins(EmailHarness):

    def test_no_scheduled_payins(self):
        self.make_participant('alice')
        send_upcoming_debit_notifications()
        execute_scheduled_payins()
        notifs = self.db.all("SELECT * FROM notifications")
        assert not notifs
        payins = self.db.all("SELECT * FROM payins")
        assert not payins

    def test_one_scheduled_payin(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, EUR('3.00'), renewal_mode=2)
        alice_card = self.attach_stripe_payment_method(alice, 'pm_card_visa')
        self.make_payin_and_transfer(alice_card, bob, EUR('12.00'))
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 1
        assert scheduled_payins[0].amount == EUR('12.00')

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '14 days')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €12.00'

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
        """)
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

    def test_multiple_scheduled_payins(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        dana = self.make_participant('dana')
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

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '14 days')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debit of €37.00'

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
        """)
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

    def test_canceled_and_impossible_transfers(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        dana = self.make_participant('dana')
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

        bob.close(None)
        self.db.run("UPDATE participants SET is_suspended = true WHERE username = 'carl'")
        self.db.run("UPDATE tips SET renewal_mode = 1 WHERE tippee = %s", (dana.id,))

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = (current_date + interval '14 days')
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: upcoming debits totaling €28.00'

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
        """)
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 3
        emails = self.get_emails()
        assert len(emails) == 2
        assert emails[0]['to'] == ['alice <alice@liberapay.com>']
        assert emails[0]['subject'] == 'Liberapay donation renewal: payment aborted'
        assert emails[1]['to'] == ['alice <alice@liberapay.com>']
        assert emails[1]['subject'] == 'Liberapay donation renewal: payment aborted'

    def test_canceled_scheduled_payin(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
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
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 0
        scheduled_payins = self.db.all("SELECT * FROM scheduled_payins ORDER BY id")
        assert len(scheduled_payins) == 0

    def test_scheduled_payin_suspended_payer(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob')
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
        """)
        send_upcoming_debit_notifications()
        emails = self.get_emails()
        assert len(emails) == 0

        self.db.run("""
            UPDATE scheduled_payins
               SET execution_date = current_date
                 , last_notif_ts = (last_notif_ts - interval '14 days')
        """)
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 1
        assert payins[0].payer == alice.id
        assert payins[0].amount == EUR('43.00')
        assert payins[0].off_session is False
        emails = self.get_emails()
        assert len(emails) == 0

    def test_missing_route(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob')
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
        """)
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
        execute_scheduled_payins()
        payins = self.db.all("SELECT * FROM payins ORDER BY ctime")
        assert len(payins) == 1
        assert payins[0].payer == alice.id
        assert payins[0].amount == EUR('30.00')
        assert payins[0].off_session is False
