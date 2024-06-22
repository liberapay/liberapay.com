from unittest import mock

import pytest

from liberapay.billing.payday import create_payday_issue, main, NoPayday, Payday
from liberapay.constants import EVENTS
from liberapay.i18n.currencies import MoneyBasket
from liberapay.models.participant import Participant
from liberapay.testing import EUR, JPY, USD, Foobar, website
from liberapay.testing.emails import EmailHarness


class TestPayday(EmailHarness):

    def setUp(self):
        super().setUp()
        self.david = self.make_participant('david', email='david@example.org')
        self.janet = self.make_participant('janet', email='janet@example.net')
        self.janet_route = self.upsert_route(self.janet, 'stripe-card')
        self.homer = self.make_participant('homer', email='homer@example.com')
        self.homer_route = self.upsert_route(self.homer, 'stripe-sdd')

    def test_payday_prevents_human_errors(self):
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            lock = cursor.one("SELECT pg_try_advisory_lock(1)")
            assert lock  # sanity check
            with self.assertRaises(AssertionError) as cm:
                main()
            assert cm.exception.args[0] == "failed to acquire the payday lock"

        main()

        with self.assertRaises(AssertionError) as cm:
            main()
        assert cm.exception.args[0] == "payday has already been run this week"

        admin = self.make_participant('admin', privileges=1)
        r = self.client.PxST('/admin/payday', data={'action': 'run_payday'}, auth_as=admin)
        assert r.code == 403
        assert r.text == "it's not time to run payday"

    @mock.patch('liberapay.billing.payday.exec_payday')
    @mock.patch.object(Payday, 'transfer_for_real')
    def test_payday_can_be_restarted_after_crash(self, transfer_for_real, exec_payday):
        transfer_for_real.side_effect = Foobar
        self.janet.set_tip_to(self.homer, EUR('6.00'))
        with self.assertRaises(Foobar):
            Payday.start().run()
        # Check that the web interface allows relaunching
        admin = self.make_participant('admin', privileges=1)
        r = self.client.PxST('/admin/payday', data={'action': 'rerun_payday'}, auth_as=admin)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/admin/payday/1'
        assert exec_payday.call_count == 1
        # Test actually relaunching
        transfer_for_real.side_effect = None
        Payday.start().run()

    def test_payday_log_can_be_accessed(self):
        _override_payday_checks = website.env.override_payday_checks
        website.env.override_payday_checks = True
        try:
            alice = self.make_participant('alice', privileges=1)
            r = self.client.PxST('/admin/payday', data={'action': 'run_payday'}, auth_as=alice)
            assert r.code == 302
            assert r.headers[b'Location'] == b'/admin/payday/1'
        finally:
            website.env.override_payday_checks = _override_payday_checks
        r = self.client.GET('/admin/payday/1', auth_as=alice)
        assert r.code == 200
        r = self.client.GxT(
            '/admin/payday/1.txt',
            HTTP_RANGE=b'x-lines=0-', HTTP_ACCEPT=b'text/plain',
            auth_as=alice,
        )
        assert r.code == 206
        assert r.headers[b'Content-Type'] == b'text/plain'

    def test_payday_id_is_serial(self):
        for i in range(1, 4):
            self.db.run("SELECT nextval('paydays_id_seq')")
            main(override_payday_checks=True)
            id = self.db.one("SELECT id FROM paydays ORDER BY id DESC LIMIT 1")
            assert id == i

    def test_payday_start(self):
        payday1 = Payday.start()
        payday2 = Payday.start()
        assert payday1.__dict__ == payday2.__dict__

    def test_payday_can_be_resumed_at_any_stage(self):
        payday = Payday.start()
        with mock.patch.object(Payday, 'clean_up') as f:
            f.side_effect = Foobar
            with self.assertRaises(Foobar):
                payday.run()
        assert payday.stage == 2
        with mock.patch.object(Payday, 'recompute_stats') as f:
            f.side_effect = Foobar
            with self.assertRaises(Foobar):
                payday.run()
        assert payday.stage == 3
        with mock.patch('liberapay.payin.cron.send_donation_reminder_notifications') as f:
            f.side_effect = Foobar
            with self.assertRaises(Foobar):
                payday.run()
        assert payday.stage == 4
        with mock.patch.object(Payday, 'generate_payment_account_required_notifications') as f:
            f.side_effect = Foobar
            with self.assertRaises(Foobar):
                payday.run()
        assert payday.stage == 5
        payday.run()
        assert payday.stage is None

    def test_update_cached_amounts(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        alice_card = self.upsert_route(alice, 'stripe-card')
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        carl_card = self.upsert_route(carl, 'stripe-card')
        dana = self.make_participant('dana')
        emma = Participant.make_stub(username='emma')
        team2 = self.make_participant('team2', kind='group')
        team2.add_member(dana)
        alice.set_tip_to(dana, EUR('3.00'))
        self.make_payin_and_transfer(alice_card, dana, EUR('30.00'))
        alice.set_tip_to(bob, EUR('6.00'))
        self.make_payin_and_transfer(alice_card, bob, EUR('60.00'))
        alice.set_tip_to(emma, EUR('0.50'))
        alice.set_tip_to(team, EUR('1.20'))
        alice.set_tip_to(team2, EUR('0.49'))
        self.make_payin_and_transfer(alice_card, team2, EUR('4.90'))
        bob.set_tip_to(alice, EUR('5.00'))
        team.set_take_for(bob, EUR('1.00'), team)
        self.make_payin_and_transfer(alice_card, team, EUR('12.00'))
        bob.set_tip_to(dana, EUR('2.00'))  # funded by bob's take
        bob.set_tip_to(emma, EUR('7.00'))  # not funded, insufficient receiving
        carl.set_tip_to(dana, EUR('2.08'))  # not funded, insufficient balance
        self.make_payin_and_transfer(carl_card, dana, EUR('1.56'))
        fred = self.make_participant('fred')
        fred_card = self.upsert_route(fred, 'stripe-card')
        fred.set_tip_to(dana, EUR('2.22'))
        self.make_payin_and_transfer(fred_card, dana, EUR('8.88'))
        self.db.run("UPDATE participants SET is_suspended = true WHERE username = 'fred'")
        dana.update_receiving()

        def check():
            alice = Participant.from_username('alice')
            bob = Participant.from_username('bob')
            carl = Participant.from_username('carl')
            dana = Participant.from_username('dana')
            emma = Participant.from_username('emma')
            assert alice.giving == EUR('10.69')
            assert alice.receiving == EUR('0.00')
            assert alice.npatrons == 0
            assert alice.nteampatrons == 0
            assert bob.giving == EUR('0.00')
            assert bob.taking == EUR('1.00')
            assert bob.receiving == EUR('7.00')
            assert bob.npatrons == 1
            assert bob.nteampatrons == 1
            assert carl.giving == EUR('0.00')
            assert carl.receiving == EUR('0.00')
            assert carl.npatrons == 0
            assert carl.nteampatrons == 0
            assert dana.receiving == EUR('3.49')
            assert dana.npatrons == 1
            assert dana.nteampatrons == 1
            assert emma.receiving == EUR('0.50')
            assert emma.npatrons == 1
            assert emma.nteampatrons == 0
            funded_tips = self.db.all("SELECT amount FROM tips WHERE is_funded ORDER BY id")
            assert funded_tips == [3, 6, 0.5, EUR('1.20'), EUR('0.49'), EUR('2.22')]

            team = Participant.from_username('team')
            assert team.receiving == EUR('1.20')
            assert team.npatrons == 1
            assert team.leftover == EUR('0.20')

            team2 = Participant.from_username('team2')
            assert team2.receiving == EUR('0.49')
            assert team2.npatrons == 1
            assert team2.leftover == EUR('0.00')

            janet = self.janet.refetch()
            assert janet.giving == 0
            assert janet.receiving == 0
            assert janet.taking == 0
            assert janet.npatrons == 0
            assert janet.nteampatrons == 0

        # Pre-test check
        check()

        # Check that update_cached_amounts doesn't mess anything up
        Payday.start().update_cached_amounts()
        check()

        # Check that update_cached_amounts actually updates amounts
        self.db.run("""
            UPDATE tips t
               SET is_funded = true
              FROM participants p
             WHERE p.id = t.tippee;
            UPDATE participants
               SET giving = (10000,'EUR')
                 , taking = (10000,'EUR')
             WHERE kind NOT IN ('group', 'community');
            UPDATE participants
               SET npatrons = 10000
                 , receiving = (10000,'EUR');
        """)
        Payday.start().update_cached_amounts()
        check()

        # Check that the update methods of Participant concur
        for p in self.db.all("SELECT p.*::participants FROM participants p"):
            p.update_receiving()
            p.update_giving()
        check()

    def test_prepare(self):
        self.clear_tables()
        self.make_participant('carl')

        payday = Payday.start()
        ts_start = payday.ts_start

        get_participants = lambda c: c.all("SELECT * FROM payday_participants")

        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, ts_start)
            participants = get_participants(cursor)

        # run a second time, we should see it pick up the existing payday
        payday = Payday.start()
        second_ts_start = payday.ts_start
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, second_ts_start)
            second_participants = get_participants(cursor)

        assert ts_start == second_ts_start
        participants = list(participants)
        second_participants = list(second_participants)

        # carl is the only participant
        assert len(participants) == 1
        assert participants == second_participants

    def test_end(self):
        Payday.start().end()
        result = self.db.one("SELECT count(*) FROM paydays "
                             "WHERE ts_end > '1970-01-01'")
        assert result == 1

    def test_end_raises_NoPayday(self):
        with self.assertRaises(NoPayday):
            Payday().end()

    def test_payday_reduces_advance_even_when_tippee_goal_is_negative(self):
        self.janet.set_tip_to(self.homer, EUR('13.00'))
        self.make_payin_and_transfer(self.janet_route, self.homer, EUR('20.00'))
        self.db.run("UPDATE participants SET goal = (-1,null) WHERE username='homer'")
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_virtually(cursor, payday.ts_start, payday.id)
            transfer = cursor.one("SELECT * FROM payday_transfers")
            assert transfer.amount == EUR('13.00')

    def test_payday_doesnt_make_null_transfers(self):
        alice = self.make_participant('alice')
        alice.set_tip_to(self.homer, EUR('1.00'))
        alice.set_tip_to(self.homer, EUR(0))
        a_team = self.make_participant('a_team', kind='group')
        a_team.add_member(alice)
        Payday.start().run()
        transfers0 = self.db.all("SELECT * FROM transfers WHERE amount = 0")
        assert not transfers0

    def test_transfer_tips(self):
        david_card = self.upsert_route(self.david, 'stripe-card')
        self.david.set_tip_to(self.janet, EUR('0.51'))
        self.make_payin_and_transfer(david_card, self.janet, EUR('51.00'))
        self.david.set_tip_to(self.homer, EUR('0.50'))
        self.make_payin_and_transfer(david_card, self.homer, EUR('0.49'))
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_virtually(cursor, payday.ts_start, payday.id)
            tips = dict(cursor.all("SELECT tippee, is_funded FROM payday_tips"))
            assert tips == {
                self.janet.id: True,
                self.homer.id: False,
            }
            transfers = dict(cursor.all("SELECT tippee, context FROM payday_transfers"))
            assert transfers == {
                self.janet.id: 'tip',
                self.homer.id: 'partial-tip',
            }

    def test_payday_handles_paid_in_advance(self):
        self.david.update_bit('email_notif_bits', EVENTS['income'].bit, True)
        self.homer.update_bit('email_notif_bits', EVENTS['income'].bit, True)
        self.add_payment_account(self.david, 'stripe')
        self.add_payment_account(self.homer, 'stripe')
        self.janet.set_tip_to(self.david, EUR('0.60'))
        self.make_payin_and_transfer(self.janet_route, self.david, EUR('1.20'))
        team = self.make_participant('team', kind='group')
        team.set_take_for(self.homer, EUR('0.40'), team)
        self.janet.set_tip_to(team, EUR('0.40'))
        self.make_payin_and_transfer(self.janet_route, team, EUR('0.80'))

        # Run a payday and check the results
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = current_date
        """)
        Payday.start().run()
        tips = self.db.all("""
            SELECT *
              FROM current_tips
             WHERE tipper = %s
          ORDER BY id
        """, (self.janet.id,))
        assert len(tips) == 2
        assert tips[0].paid_in_advance == EUR('0.60')
        assert tips[1].paid_in_advance == EUR('0.40')
        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 2

        emails = self.get_emails()
        assert len(emails) == 3
        assert emails[0]['to'][0] == 'david <%s>' % self.david.email
        assert '0.60' in emails[0]['subject']
        assert emails[1]['to'][0] == 'homer <%s>' % self.homer.email
        assert '0.40' in emails[1]['text']
        assert emails[2]['to'][0] == 'janet <%s>' % self.janet.email
        assert 'renew your donation' in emails[2]['subject']
        assert '2 donations' in emails[2]['text']

        # Now run a second payday and check the results again
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")
        Payday.start().run()
        tips = self.db.all("""
            SELECT *
              FROM current_tips
             WHERE tipper = %s
          ORDER BY id
        """, (self.janet.id,))
        assert len(tips) == 2
        assert not tips[0].paid_in_advance
        assert not tips[1].paid_in_advance
        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 4

        emails = self.get_emails()
        assert len(emails) == 2
        assert emails[0]['to'][0] == 'david <%s>' % self.david.email
        assert '0.60' in emails[0]['subject']
        assert emails[1]['to'][0] == 'homer <%s>' % self.homer.email
        assert '0.40' in emails[1]['text']

    def test_payday_notifies_participants(self):
        self.david.update_bit('email_notif_bits', EVENTS['income'].bit, True)
        self.janet.set_tip_to(self.david, EUR('4.50'))
        self.janet.set_tip_to(self.homer, EUR('3.50'))
        team = self.make_participant('team', kind='group', email='team@example.com')
        self.janet.set_tip_to(team, EUR('0.25'))
        team.add_member(self.david)
        team.set_take_for(self.david, EUR('0.23'), team)
        janet_card = self.upsert_route(self.janet, 'stripe-card')
        self.make_payin_and_transfer(janet_card, self.david, EUR('4.50'))
        self.make_payin_and_transfer(janet_card, self.homer, EUR('3.50'))
        self.make_payin_and_transfer(janet_card, team, EUR('25.00'))
        self.client.POST('/homer/emails/', auth_as=self.homer,
                         data={'events': 'income', 'income': ''}, json=True)
        self.db.run("""
            UPDATE scheduled_payins
               SET ctime = ctime - interval '12 hours'
                 , execution_date = execution_date - interval '2 weeks'
        """)
        Payday.start().run()
        emails = self.get_emails()
        assert len(emails) == 2
        assert emails[0]['to'][0] == 'david <%s>' % self.david.email
        assert '4.73' in emails[0]['subject']
        assert emails[1]['to'][0] == 'janet <%s>' % self.janet.email
        assert 'renew your donation' in emails[1]['subject']
        assert '2 donations' in emails[1]['text']

    def test_log_upload(self):
        payday = Payday.start()
        with open('payday-%i.txt.part' % payday.id, 'w') as f:
            f.write('fake log file\n')
        with mock.patch.object(self.website, 's3') as s3:
            payday.run('.', keep_log=True)
            assert s3.upload_file.call_count == 1

    @mock.patch('liberapay.billing.payday.date')
    @mock.patch('liberapay.website.website.platforms.github.api_get')
    @mock.patch('liberapay.website.website.platforms.github.api_request')
    def test_create_payday_issue(self, api_request, api_get, date):
        date.today.return_value.isoweekday.return_value = 3
        # 1st payday issue
        api_get.return_value.json = lambda: []
        repo = self.website.app_conf.payday_repo
        html_url = 'https://github.com/%s/issues/1' % repo
        api_request.return_value.json = lambda: {'html_url': html_url}
        create_payday_issue()
        args = api_request.call_args
        post_path = '/repos/%s/issues' % repo
        assert args[0] == ('POST', '', post_path)
        assert args[1]['json'] == {'body': '', 'title': 'Payday #1', 'labels': ['Payday']}
        assert args[1]['sess'].auth
        public_log = self.db.one("SELECT public_log FROM paydays")
        assert public_log == html_url
        api_request.reset_mock()
        # Check that executing the function again doesn't create a duplicate
        create_payday_issue()
        assert api_request.call_count == 0
        # Run 1st payday
        Payday.start().run()
        # 2nd payday issue
        api_get.return_value.json = lambda: [{'body': 'Lorem ipsum', 'title': 'Payday #1'}]
        html_url = 'https://github.com/%s/issues/2' % repo
        api_request.return_value.json = lambda: {'html_url': html_url}
        create_payday_issue()
        args = api_request.call_args
        assert args[0] == ('POST', '', post_path)
        assert args[1]['json'] == {'body': 'Lorem ipsum', 'title': 'Payday #2', 'labels': ['Payday']}
        assert args[1]['sess'].auth
        public_log = self.db.one("SELECT public_log FROM paydays WHERE id = 2")
        assert public_log == html_url


class TestPaydayForTeams(EmailHarness):

    def get_taken_sums(self):
        return dict(self.db.all("""
            SELECT tippee, basket_sum(amount)
              FROM transfers
             WHERE context = 'take'
          GROUP BY tippee
        """))

    def get_tip_advances(self):
        return dict(self.db.all("SELECT tipper, paid_in_advance FROM current_tips"))

    def test_transfer_takes(self):
        a_team = self.make_participant('a_team', kind='group')
        alice = self.make_participant('alice')
        self.add_payment_account(alice, 'stripe')
        a_team.set_take_for(alice, EUR('1.00'), a_team)
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        a_team.set_take_for(bob, EUR('0.01'), a_team)
        charlie = self.make_participant('charlie')
        charlie.set_tip_to(a_team, EUR('1.01'))
        charlie_card = self.upsert_route(charlie, 'stripe-card')
        self.make_payin_and_transfer(charlie_card, a_team, EUR('10.00'))

        payday = Payday.start()

        # Test that payday ignores takes set after it started
        a_team.set_take_for(alice, EUR('2.00'), a_team)

        # Run the transfer multiple times to make sure we ignore takes that
        # have already been processed
        with mock.patch.object(payday, 'transfer_for_real') as f:
            f.side_effect = Foobar
            with self.assertRaises(Foobar):
                payday.shuffle()
        for i in range(2):
            payday.shuffle()

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('1.00'),
            bob.id: EUR('0.01'),
        }

    def test_underfunded_team(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        self.add_payment_account(alice, 'stripe')
        team.set_take_for(alice, EUR('1.00'), team)
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        team.set_take_for(bob, EUR('1.00'), team)
        charlie = self.make_participant('charlie')
        charlie.set_tip_to(team, EUR('0.26'))
        charlie_card = self.upsert_route(charlie, 'stripe-card')
        self.make_payin_and_transfer(charlie_card, team, EUR('26.00'))

        Payday.start().run()

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.13'),
            bob.id: EUR('0.13'),
        }

    def test_wellfunded_team(self):
        """
        This tests two properties:
        - takes are maximums
        - donors all pay their share, the first donor doesn't pay everything
        """
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        self.add_payment_account(alice, 'stripe')
        team.set_take_for(alice, EUR('0.79'), team)
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        team.set_take_for(bob, EUR('0.21'), team)
        charlie = self.make_participant('charlie')
        charlie.set_tip_to(team, EUR('5.00'))
        charlie_card = self.upsert_route(charlie, 'stripe-card')
        self.make_payin_and_transfer(charlie_card, team, EUR('10.00'))
        dan = self.make_participant('dan')
        dan.set_tip_to(team, EUR('5.00'))
        dan_card = self.upsert_route(dan, 'stripe-card')
        self.make_payin_and_transfer(dan_card, team, EUR('10.00'))

        Payday.start().run()

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.79'),
            bob.id: EUR('0.21'),
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('9.5')
        assert dan_tip.paid_in_advance == EUR('9.5')

    def test_wellfunded_team_with_early_donor(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        self.add_payment_account(alice, 'stripe')
        team.set_take_for(alice, EUR('0.79'), team)
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        team.set_take_for(bob, EUR('0.21'), team)
        charlie = self.make_participant('charlie')
        charlie.set_tip_to(team, EUR('2.00'))
        charlie_card = self.upsert_route(charlie, 'stripe-card')
        self.make_payin_and_transfer(charlie_card, team, EUR('10.00'))

        print("> Step 1: three weeks of donations from charlie only")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.79') * 3,
            bob.id: EUR('0.21') * 3,
        }
        charlie_tip = charlie.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('7.00')

        print("> Step 2: dan joins the party, charlie's donation is automatically "
              "reduced while dan catches up")
        print()
        dan = self.make_participant('dan')
        dan.set_tip_to(team, EUR('2.00'))
        dan_card = self.upsert_route(dan, 'stripe-card')
        self.make_payin_and_transfer(dan_card, team, EUR('10.00'))

        for i in range(6):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.79') * 9,
            bob.id: EUR('0.21') * 9,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('5.50')
        assert dan_tip.paid_in_advance == EUR('5.50')

        print("> Step 3: dan has caught up with charlie, they will now both give 0.50")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.79') * 12,
            bob.id: EUR('0.21') * 12,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('4.00')
        assert dan_tip.paid_in_advance == EUR('4.00')

    def test_wellfunded_team_with_two_early_donors(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        self.add_payment_account(alice, 'stripe')
        team.set_take_for(alice, EUR('0.79'), team)
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        team.set_take_for(bob, EUR('0.21'), team)
        charlie = self.make_participant('charlie')
        charlie.set_tip_to(team, EUR('1.00'))
        charlie_card = self.upsert_route(charlie, 'stripe-card')
        self.make_payin_and_transfer(charlie_card, team, EUR('10.00'))
        dan = self.make_participant('dan')
        dan.set_tip_to(team, EUR('3.00'))
        dan_card = self.upsert_route(dan, 'stripe-card')
        self.make_payin_and_transfer(dan_card, team, EUR('10.00'))

        print("> Step 1: three weeks of donations from early donors")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.79') * 3,
            bob.id: EUR('0.21') * 3,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('9.25')
        assert dan_tip.paid_in_advance == EUR('7.75')

        print("> Step 2: a new donor appears, the contributions of the early "
              "donors automatically decrease while the new donor catches up")
        print()
        emma = self.make_participant('emma')
        emma.set_tip_to(team, EUR('1.00'))
        emma_card = self.upsert_route(emma, 'stripe-card')
        self.make_payin_and_transfer(emma_card, team, EUR('10.00'))

        Payday.start().run(recompute_stats=0, update_cached_amounts=False)
        print()
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.79') * 4,
            bob.id: EUR('0.21') * 4,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        emma_tip = emma.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('9.19')
        assert dan_tip.paid_in_advance == EUR('7.59')
        assert emma_tip.paid_in_advance == EUR('9.22')

        Payday.start().run(recompute_stats=0, update_cached_amounts=False)
        print()
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.79') * 5,
            bob.id: EUR('0.21') * 5,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        emma_tip = emma.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('8.99')
        assert dan_tip.paid_in_advance == EUR('7.01')
        assert emma_tip.paid_in_advance == EUR('9.00')

        print("> Step 3: emma has caught up with the early donors")
        print()

        for i in range(2):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.79') * 7,
            bob.id: EUR('0.21') * 7,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        emma_tip = emma.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('8.60')
        assert dan_tip.paid_in_advance == EUR('5.80')
        assert emma_tip.paid_in_advance == EUR('8.60')

    def test_wellfunded_team_with_two_early_donors_and_low_amounts(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        self.add_payment_account(alice, 'stripe')
        team.set_take_for(alice, EUR('0.01'), team)
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        team.set_take_for(bob, EUR('0.01'), team)
        charlie = self.make_participant('charlie')
        charlie.set_tip_to(team, EUR('0.02'))
        charlie_card = self.upsert_route(charlie, 'stripe-card')
        self.make_payin_and_transfer(charlie_card, team, EUR('10.00'))
        dan = self.make_participant('dan')
        dan.set_tip_to(team, EUR('0.02'))
        dan_card = self.upsert_route(dan, 'stripe-card')
        self.make_payin_and_transfer(dan_card, team, EUR('10.00'))

        print("> Step 1: three weeks of donations from early donors")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.01') * 3,
            bob.id: EUR('0.01') * 3,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('9.97')
        assert dan_tip.paid_in_advance == EUR('9.97')

        print("> Step 2: a new donor appears, the contributions of the early "
              "donors automatically decrease while the new donor catches up")
        print()
        emma = self.make_participant('emma')
        emma.set_tip_to(team, EUR('0.02'))
        emma_card = self.upsert_route(emma, 'stripe-card')
        self.make_payin_and_transfer(emma_card, team, EUR('10.00'))

        for i in range(6):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.01') * 9,
            bob.id: EUR('0.01') * 9,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        emma_tip = emma.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('9.94')
        assert dan_tip.paid_in_advance == EUR('9.94')
        assert emma_tip.paid_in_advance == EUR('9.94')

    def test_wellfunded_team_with_early_donor_and_small_leftover(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        self.add_payment_account(alice, 'stripe')
        team.set_take_for(alice, EUR('0.50'), team)
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        team.set_take_for(bob, EUR('0.50'), team)
        charlie = self.make_participant('charlie')
        charlie.set_tip_to(team, EUR('0.52'))
        charlie_card = self.upsert_route(charlie, 'stripe-card')
        self.make_payin_and_transfer(charlie_card, team, EUR('10.00'))

        print("> Step 1: three weeks of donations from early donor")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.26') * 3,
            bob.id: EUR('0.26') * 3,
        }
        charlie_tip = charlie.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('8.44')

        print("> Step 2: a new donor appears, the contribution of the early "
              "donor automatically decreases while the new donor catches up, "
              "but the leftover is small so the adjustments are limited")
        print()
        dan = self.make_participant('dan')
        dan.set_tip_to(team, EUR('0.52'))
        dan_card = self.upsert_route(dan, 'stripe-card')
        self.make_payin_and_transfer(dan_card, team, EUR('10.00'))

        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()
            self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.26') * 3 + EUR('0.50') * 3,
            bob.id: EUR('0.26') * 3 + EUR('0.50') * 3,
        }
        charlie_tip = charlie.get_tip_to(team)
        dan_tip = dan.get_tip_to(team)
        assert charlie_tip.paid_in_advance == EUR('7.00')
        assert dan_tip.paid_in_advance == EUR('8.44')

    @pytest.mark.xfail(reason="Payday.resolve_takes() currently isn't clever enough")
    def test_mutual_tipping_through_teams(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        self.add_payment_account(alice, 'stripe')
        alice.set_tip_to(team, EUR('2.00'))
        team.set_take_for(alice, EUR('0.25'), team)
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        bob.set_tip_to(team, EUR('2.00'))
        team.set_take_for(bob, EUR('0.75'), team)

        alice_card = self.upsert_route(alice, 'stripe-card')
        self.make_payin_and_transfer(alice_card, team, EUR('8.00'))
        bob_card = self.upsert_route(bob, 'stripe-card')
        self.make_payin_and_transfer(bob_card, team, EUR('10.00'))

        Payday.start().run()

        taken = self.get_taken_sums()
        assert taken == {
            alice.id: EUR('0.25'),
            bob.id: EUR('0.75'),
        }
        alice_tip = alice.get_tip_to(team)
        bob_tip = bob.get_tip_to(team)
        assert alice_tip.paid_in_advance == EUR('7.25')
        assert bob_tip.paid_in_advance == EUR('9.75')

    def get_payday_transfers(self):
        return self.db.all("""
            SELECT tippee, amount
              FROM transfers tr
             WHERE tr.timestamp > (
                       SELECT ts_start
                         FROM paydays
                     ORDER BY ts_start DESC
                        LIMIT 1
                   )
        """)

    def test_indivisible_team_income(self):
        # Create a team with 7 members
        member_1 = self.make_participant('member_1')
        member_2 = self.make_participant('member_2')
        member_3 = self.make_participant('member_3')
        member_4 = self.make_participant('member_4')
        member_5 = self.make_participant('member_5')
        member_6 = self.make_participant('member_6')
        member_7 = self.make_participant('member_7')
        self.add_payment_account(member_1, 'stripe')
        self.add_payment_account(member_2, 'stripe')
        self.add_payment_account(member_3, 'stripe')
        self.add_payment_account(member_4, 'stripe')
        self.add_payment_account(member_5, 'stripe')
        self.add_payment_account(member_6, 'stripe')
        self.add_payment_account(member_7, 'stripe')
        team = self.make_participant('team', kind='group')
        team.set_take_for(member_1, EUR('1.00'), team)
        team.set_take_for(member_2, EUR('1.00'), team)
        team.set_take_for(member_3, EUR('1.00'), team)
        team.set_take_for(member_4, EUR('1.00'), team)
        team.set_take_for(member_5, EUR('1.00'), team)
        team.set_take_for(member_6, EUR('1.00'), team)
        team.set_take_for(member_7, EUR('1.00'), team)

        # Fund the team
        charlie = self.make_participant('charlie')
        charlie.set_tip_to(team, EUR('0.85'))
        charlie_card = self.upsert_route(charlie, 'stripe-card')
        payin_transfers = self.make_payin_and_transfer(charlie_card, team, EUR('85.00'))[1]
        transfer_amounts = {pt.recipient: pt.amount for pt in payin_transfers}
        assert transfer_amounts == {
            member_1.id: EUR('12.15'),
            member_2.id: EUR('12.15'),
            member_3.id: EUR('12.14'),
            member_4.id: EUR('12.14'),
            member_5.id: EUR('12.14'),
            member_6.id: EUR('12.14'),
            member_7.id: EUR('12.14'),
        }

        # First payday
        Payday.start().run()
        transfer_amounts = dict(self.get_payday_transfers())
        assert transfer_amounts == {
            member_1.id: EUR('0.13'),
            member_2.id: EUR('0.12'),
            member_3.id: EUR('0.12'),
            member_4.id: EUR('0.12'),
            member_5.id: EUR('0.12'),
            member_6.id: EUR('0.12'),
            member_7.id: EUR('0.12'),
        }
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        # Second payday
        Payday.start().run()
        transfer_amounts = dict(self.get_payday_transfers())
        assert transfer_amounts == {
            member_1.id: EUR('0.12'),
            member_2.id: EUR('0.13'),
            member_3.id: EUR('0.12'),
            member_4.id: EUR('0.12'),
            member_5.id: EUR('0.12'),
            member_6.id: EUR('0.12'),
            member_7.id: EUR('0.12'),
        }
        self.db.run("UPDATE notifications SET ts = ts - interval '1 week'")

        # Third payday, with an income increased by four cents
        charlie.set_tip_to(team, EUR('0.89'))
        Payday.start().run()
        transfer_amounts = dict(self.get_payday_transfers())
        assert transfer_amounts == {
            member_1.id: EUR('0.12'),
            member_2.id: EUR('0.12'),
            member_3.id: EUR('0.13'),
            member_4.id: EUR('0.13'),
            member_5.id: EUR('0.13'),
            member_6.id: EUR('0.13'),
            member_7.id: EUR('0.13'),
        }

    # Two currencies
    # ==============

    def set_up_team_with_two_currencies(self):
        team = self.team = self.make_participant(
            'team', kind='group', accepted_currencies='EUR,USD'
        )
        self.alice = self.make_participant('alice', main_currency='EUR',
                                           accepted_currencies='EUR,USD')
        self.add_payment_account(self.alice, 'stripe')
        team.set_take_for(self.alice, EUR('1.00'), team)
        self.bob = self.make_participant('bob', main_currency='USD',
                                         accepted_currencies='EUR,USD')
        self.add_payment_account(self.bob, 'stripe')
        team.set_take_for(self.bob, EUR('1.00'), team)
        self.donor1_eur = self.make_participant('donor1_eur')
        self.donor2_usd = self.make_participant('donor2_usd')
        self.donor3_eur = self.make_participant('donor3_eur')
        self.donor4_usd = self.make_participant('donor4_usd')
        self.donor1_eur_route = self.upsert_route(self.donor1_eur, 'stripe-card')
        self.donor2_usd_route = self.upsert_route(self.donor2_usd, 'stripe-card')
        self.donor3_eur_route = self.upsert_route(self.donor3_eur, 'stripe-card')
        self.donor4_usd_route = self.upsert_route(self.donor4_usd, 'stripe-card')

    def test_transfer_takes_with_two_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('0.50'))
        self.donor2_usd.set_tip_to(self.team, USD('0.60'))
        self.donor3_eur.set_tip_to(self.team, EUR('0.50'))
        self.donor4_usd.set_tip_to(self.team, USD('0.60'))
        self.make_payin_and_transfer(self.donor1_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor2_usd_route, self.team, USD(100))
        self.make_payin_and_transfer(self.donor3_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor4_usd_route, self.team, USD(100))

        Payday.start().shuffle()

        taken = self.get_taken_sums()
        assert taken == {
            self.alice.id: EUR('1.00'),
            self.bob.id: USD('1.20'),
        }
        tip_advances = self.get_tip_advances()
        assert tip_advances == {
            self.donor1_eur.id: EUR('99.50'),
            self.donor2_usd.id: USD('99.40'),
            self.donor3_eur.id: EUR('99.50'),
            self.donor4_usd.id: USD('99.40'),
        }

    def test_transfer_takes_with_two_currencies_on_both_sides(self):
        self.set_up_team_with_two_currencies()
        self.team.set_take_for(self.alice, EUR('0.01'), self.alice)
        self.team.set_take_for(self.bob, USD('0.01'), self.bob)
        self.donor1_eur.set_tip_to(self.team, EUR('0.01'))
        self.donor2_usd.set_tip_to(self.team, USD('0.01'))
        self.make_payin_and_transfer(self.donor1_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor2_usd_route, self.team, USD(100))

        Payday.start().shuffle()

        taken = self.get_taken_sums()
        assert taken == {
            self.alice.id: EUR('0.01'),
            self.bob.id: USD('0.01'),
        }
        tip_advances = self.get_tip_advances()
        assert tip_advances == {
            self.donor1_eur.id: EUR('99.99'),
            self.donor2_usd.id: USD('99.99'),
        }

    def test_wellfunded_team_with_two_balanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('1.00'))
        self.donor2_usd.set_tip_to(self.team, USD('1.20'))
        self.donor3_eur.set_tip_to(self.team, EUR('1.00'))
        self.donor4_usd.set_tip_to(self.team, USD('1.20'))
        self.make_payin_and_transfer(self.donor1_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor2_usd_route, self.team, USD(100))
        self.make_payin_and_transfer(self.donor3_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor4_usd_route, self.team, USD(100))

        Payday.start().shuffle()

        taken = self.get_taken_sums()
        assert taken == {
            self.alice.id: EUR('1.00'),
            self.bob.id: USD('1.20'),
        }
        tip_advances = self.get_tip_advances()
        assert tip_advances == {
            self.donor1_eur.id: EUR('99.50'),
            self.donor2_usd.id: USD('99.40'),
            self.donor3_eur.id: EUR('99.50'),
            self.donor4_usd.id: USD('99.40'),
        }

    def test_exactly_funded_team_with_two_unbalanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('0.75'))
        self.donor2_usd.set_tip_to(self.team, USD('0.30'))
        self.donor3_eur.set_tip_to(self.team, EUR('0.75'))
        self.donor4_usd.set_tip_to(self.team, USD('0.30'))
        self.make_payin_and_transfer(self.donor1_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor2_usd_route, self.team, USD(100))
        self.make_payin_and_transfer(self.donor3_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor4_usd_route, self.team, USD(100))

        Payday.start().shuffle()

        taken = self.get_taken_sums()
        assert taken == {
            self.alice.id: EUR('1.00'),
            self.bob.id: MoneyBasket(EUR('0.50'), USD('0.60')),
        }
        tip_advances = self.get_tip_advances()
        assert tip_advances == {
            self.donor1_eur.id: EUR('99.25'),
            self.donor2_usd.id: USD('99.70'),
            self.donor3_eur.id: EUR('99.25'),
            self.donor4_usd.id: USD('99.70'),
        }

    def test_wellfunded_team_with_two_unbalanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('1.50'))
        self.donor2_usd.set_tip_to(self.team, USD('0.60'))
        self.donor3_eur.set_tip_to(self.team, EUR('1.50'))
        self.donor4_usd.set_tip_to(self.team, USD('0.60'))
        self.make_payin_and_transfer(self.donor1_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor2_usd_route, self.team, USD(100))
        self.make_payin_and_transfer(self.donor3_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor4_usd_route, self.team, USD(100))

        Payday.start().shuffle()

        taken = self.get_taken_sums()
        assert taken == {
            self.alice.id: EUR('1.00'),
            self.bob.id: MoneyBasket(EUR('0.50'), USD('0.60')),
        }
        tip_advances = self.get_tip_advances()
        assert tip_advances == {
            self.donor1_eur.id: EUR('99.25'),
            self.donor2_usd.id: USD('99.70'),
            self.donor3_eur.id: EUR('99.25'),
            self.donor4_usd.id: USD('99.70'),
        }

    def test_underfunded_team_with_two_balanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('0.25'))
        self.donor2_usd.set_tip_to(self.team, USD('0.30'))
        self.donor3_eur.set_tip_to(self.team, EUR('0.25'))
        self.donor4_usd.set_tip_to(self.team, USD('0.30'))
        self.make_payin_and_transfer(self.donor1_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor2_usd_route, self.team, USD(100))
        self.make_payin_and_transfer(self.donor3_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor4_usd_route, self.team, USD(100))

        Payday.start().shuffle()

        taken = self.get_taken_sums()
        assert taken == {
            self.alice.id: EUR('0.50'),
            self.bob.id: USD('0.60'),
        }
        tip_advances = self.get_tip_advances()
        assert tip_advances == {
            self.donor1_eur.id: EUR('99.75'),
            self.donor2_usd.id: USD('99.70'),
            self.donor3_eur.id: EUR('99.75'),
            self.donor4_usd.id: USD('99.70'),
        }

    def test_underfunded_team_with_two_unbalanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('0.10'))
        self.donor2_usd.set_tip_to(self.team, USD('0.25'))
        self.donor3_eur.set_tip_to(self.team, EUR('0.10'))
        self.donor4_usd.set_tip_to(self.team, USD('0.25'))
        self.make_payin_and_transfer(self.donor1_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor2_usd_route, self.team, USD(100))
        self.make_payin_and_transfer(self.donor3_eur_route, self.team, EUR(100))
        self.make_payin_and_transfer(self.donor4_usd_route, self.team, USD(100))

        Payday.start().shuffle()

        taken = self.get_taken_sums()
        assert taken == {
            self.alice.id: MoneyBasket(EUR('0.20'), USD('0.13')),
            self.bob.id: MoneyBasket(USD('0.37')),
        }
        tip_advances = self.get_tip_advances()
        assert tip_advances == {
            self.donor1_eur.id: EUR('99.90'),
            self.donor2_usd.id: USD('99.75'),
            self.donor3_eur.id: EUR('99.90'),
            self.donor4_usd.id: USD('99.75'),
        }

    # Takes paid in advance
    # =====================

    def test_takes_paid_in_advance(self):
        team = self.make_participant(
            'team', kind='group', accepted_currencies='EUR,USD'
        )
        alice = self.make_participant('alice', main_currency='EUR',
                                      accepted_currencies='EUR,USD')
        team.set_take_for(alice, EUR('1.00'), team)
        bob = self.make_participant('bob', main_currency='USD',
                                    accepted_currencies='EUR,USD')
        team.set_take_for(bob, EUR('1.00'), team)

        stripe_account_alice = self.add_payment_account(alice, 'stripe', default_currency='EUR')
        self.add_payment_account(bob, 'stripe', country='US', default_currency='USD')

        carl = self.make_participant('carl')
        carl.set_tip_to(team, EUR('10'))

        carl_card = self.upsert_route(carl, 'stripe-card')
        payin, pt = self.make_payin_and_transfer(carl_card, team, EUR('10'))
        assert pt.destination == stripe_account_alice.pk

        Payday.start().run()

        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 1
        assert transfers[0].virtual is True
        assert transfers[0].tipper == carl.id
        assert transfers[0].tippee == alice.id
        assert transfers[0].amount == EUR('1')

    def test_negative_paid_in_advance(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        team.set_take_for(alice, EUR('1.00'), team)

        stripe_account_alice = self.add_payment_account(alice, 'stripe')

        donor = self.make_participant('donor')
        donor.set_tip_to(team, EUR('5'))

        donor_card = self.upsert_route(donor, 'stripe-card')
        payin, pt = self.make_payin_and_transfer(donor_card, team, EUR('10'))
        assert pt.destination == stripe_account_alice.pk

        self.db.run("UPDATE takes SET paid_in_advance = -paid_in_advance")

        Payday.start().run()

        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 0

    def test_take_paid_in_advance_in_unaccepted_currency(self):
        team = self.make_participant('team', kind='group', accepted_currencies=None)
        alice = self.make_participant('alice', main_currency='EUR',
                                      accepted_currencies='EUR,USD')
        team.set_take_for(alice, EUR('1.00'), team)
        bob = self.make_participant('bob', main_currency='USD',
                                    accepted_currencies='EUR,USD')
        team.set_take_for(bob, USD('1.00'), team)

        stripe_account_alice = self.add_payment_account(alice, 'stripe', default_currency='EUR')
        self.add_payment_account(bob, 'stripe', country='US', default_currency='USD')

        carl = self.make_participant('carl')
        carl.set_tip_to(team, JPY('1250'))

        carl_card = self.upsert_route(carl, 'stripe-card')
        payin, pt = self.make_payin_and_transfer(carl_card, team, JPY('1250'))
        assert pt.destination == stripe_account_alice.pk

        Payday.start().run()

        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 1
        assert transfers[0].virtual is True
        assert transfers[0].tipper == carl.id
        assert transfers[0].tippee == alice.id
        assert transfers[0].amount == JPY('125')

    def test_takes_paid_in_advance_to_now_inactive_members(self):
        team = self.make_participant('team', kind='group', accepted_currencies=None)
        alice = self.make_participant('alice', main_currency='EUR', accepted_currencies=None)
        team.set_take_for(alice, EUR('1.00'), team)
        bob = self.make_participant('bob', main_currency='USD', accepted_currencies=None)
        team.set_take_for(bob, USD('1.00'), team)

        stripe_account_alice = self.add_payment_account(
            alice, 'stripe', default_currency='EUR'
        )
        stripe_account_bob = self.add_payment_account(
            bob, 'stripe', country='US', default_currency='USD'
        )

        carl = self.make_participant('carl')
        carl.set_tip_to(team, JPY('250'))

        carl_card = self.upsert_route(carl, 'stripe-card')
        payin, pt = self.make_payin_and_transfer(carl_card, team, JPY('1250'))
        assert pt.destination == stripe_account_alice.pk
        payin, pt = self.make_payin_and_transfer(carl_card, team, JPY('1250'))
        assert pt.destination == stripe_account_bob.pk

        team.set_take_for(alice, EUR('0.00'), team)
        team.set_take_for(bob, None, team)
        takes = dict(self.db.all("""
            SELECT DISTINCT ON (member)
                   member, paid_in_advance
              FROM takes
          ORDER BY member, mtime DESC
        """))
        assert takes == {
            alice.id: EUR('10.00'),
            bob.id: USD('12.00'),
        }

        Payday.start().run()

        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 2
        assert transfers[0].virtual is True
        assert transfers[0].tipper == carl.id
        assert transfers[0].tippee == alice.id
        assert transfers[0].amount == JPY('125')
        assert transfers[1].virtual is True
        assert transfers[1].tipper == carl.id
        assert transfers[1].tippee == bob.id
        assert transfers[1].amount == JPY('125')

        takes = dict(self.db.all("""
            SELECT DISTINCT ON (member)
                   member, paid_in_advance
              FROM takes
          ORDER BY member, mtime DESC
        """))
        assert takes == {
            alice.id: EUR('9.00'),
            bob.id: USD('10.80'),
        }

        notifications = self.db.all("SELECT * FROM notifications")
        assert len(notifications) == 0

        leftovers = dict(self.db.all("SELECT username, leftover FROM participants"))
        assert leftovers == {
            'team': MoneyBasket(JPY('250.00')),
            'alice': None,
            'bob': None,
            'carl': None,
        }

    def test_auto_takes_when_some_members_havent_received_enough_in_advance(self):
        team = self.make_participant('team', kind='group', accepted_currencies=None)
        member_1 = self.make_participant('member_1', main_currency='EUR', accepted_currencies=None)
        team.set_take_for(member_1, EUR(-1), team)
        member_2 = self.make_participant('member_2', main_currency='USD', accepted_currencies=None)
        team.set_take_for(member_2, USD(-1), team)
        member_3 = self.make_participant('member_3', main_currency='JPY', accepted_currencies=None)
        team.set_take_for(member_3, JPY(-1), team)

        stripe_account_member_1 = self.add_payment_account(
            member_1, 'stripe', default_currency='EUR'
        )
        stripe_account_member_2 = self.add_payment_account(
            member_2, 'stripe', country='US', default_currency='USD'
        )
        stripe_account_member_3 = self.add_payment_account(
            member_3, 'stripe', country='JP', default_currency='JPY'
        )

        donor = self.make_participant('donor')
        donor.set_tip_to(team, EUR('9.00'))

        donor_card = self.upsert_route(donor, 'stripe-card')
        payin, pt = self.make_payin_and_transfer(donor_card, team, EUR('50.00'))
        assert pt.destination == stripe_account_member_1.pk
        payin, pt = self.make_payin_and_transfer(donor_card, team, EUR('2.00'))
        assert pt.destination == stripe_account_member_2.pk
        payin, pt = self.make_payin_and_transfer(donor_card, team, EUR('3.25'))
        assert pt.destination == stripe_account_member_3.pk

        takes = team.recompute_actual_takes(self.db)
        actual_amounts = {take.member: take.actual_amount for take in takes}
        assert actual_amounts == {
            member_1.id: MoneyBasket(EUR('3.75')),
            member_2.id: MoneyBasket(EUR('2.00')),
            member_3.id: MoneyBasket(EUR('3.25')),
        }

        Payday.start().run()

        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 3
        assert transfers[0].virtual is True
        assert transfers[0].tipper == donor.id
        assert transfers[0].tippee == member_1.id
        assert transfers[0].amount == EUR('3.75')
        assert transfers[1].virtual is True
        assert transfers[1].tipper == donor.id
        assert transfers[1].tippee == member_2.id
        assert transfers[1].amount == EUR('2.00')
        assert transfers[2].virtual is True
        assert transfers[2].tipper == donor.id
        assert transfers[2].tippee == member_3.id
        assert transfers[2].amount == EUR('3.25')

        actual_amounts = dict(self.db.all("""
            SELECT member, actual_amount
              FROM current_takes
        """))
        assert actual_amounts == {
            member_1.id: MoneyBasket(EUR('9.00')),
            member_2.id: MoneyBasket(EUR('0.00')),
            member_3.id: MoneyBasket(EUR('0.00')),
        }

        leftovers = dict(self.db.all("SELECT username, leftover FROM participants"))
        assert leftovers == {
            'team': MoneyBasket(),
            'member_1': None,
            'member_2': None,
            'member_3': None,
            'donor': None,
        }

    def test_auto_takes_when_none_of_the_members_have_received_enough_in_advance(self):
        team = self.make_participant('team', kind='group', accepted_currencies=None)
        member_1 = self.make_participant('member_1')
        team.set_take_for(member_1, EUR(-1), team)
        member_2 = self.make_participant('member_2')
        team.set_take_for(member_2, EUR(-1), team)
        member_3 = self.make_participant('member_3')
        team.set_take_for(member_3, EUR(-1), team)

        stripe_account_member_1 = self.add_payment_account(
            member_1, 'stripe', default_currency='EUR'
        )
        stripe_account_member_2 = self.add_payment_account(
            member_2, 'stripe', country='US', default_currency='USD'
        )
        stripe_account_member_3 = self.add_payment_account(
            member_3, 'stripe', country='JP', default_currency='JPY'
        )

        donor = self.make_participant('donor')
        donor.set_tip_to(team, EUR('9.00'))

        donor_card = self.upsert_route(donor, 'stripe-card')
        payin, pt = self.make_payin_and_transfer(donor_card, team, EUR('1.00'))
        assert pt.destination == stripe_account_member_1.pk
        payin, pt = self.make_payin_and_transfer(donor_card, team, EUR('3.00'))
        assert pt.destination == stripe_account_member_2.pk
        payin, pt = self.make_payin_and_transfer(donor_card, team, EUR('3.01'))
        assert pt.destination == stripe_account_member_3.pk

        takes = team.recompute_actual_takes(self.db)
        actual_amounts = {take.member: take.actual_amount for take in takes}
        assert actual_amounts == {
            member_1.id: MoneyBasket(EUR('1.00')),
            member_2.id: MoneyBasket(EUR('3.00')),
            member_3.id: MoneyBasket(EUR('3.01')),
        }

        Payday.start().run()

        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 3
        assert transfers[0].virtual is True
        assert transfers[0].tipper == donor.id
        assert transfers[0].tippee == member_1.id
        assert transfers[0].amount == EUR('1.00')
        assert transfers[1].virtual is True
        assert transfers[1].tipper == donor.id
        assert transfers[1].tippee == member_2.id
        assert transfers[1].amount == EUR('3.00')
        assert transfers[2].virtual is True
        assert transfers[2].tipper == donor.id
        assert transfers[2].tippee == member_3.id
        assert transfers[2].amount == EUR('3.01')

        actual_amounts = dict(self.db.all("""
            SELECT member, actual_amount
              FROM current_takes
        """))
        assert actual_amounts == {
            member_1.id: MoneyBasket(EUR('0.00')),
            member_2.id: MoneyBasket(EUR('0.00')),
            member_3.id: MoneyBasket(EUR('0.00')),
        }

        leftovers = dict(self.db.all("SELECT username, leftover FROM participants"))
        assert leftovers == {
            'team': MoneyBasket(),
            'member_1': None,
            'member_2': None,
            'member_3': None,
            'donor': None,
        }
