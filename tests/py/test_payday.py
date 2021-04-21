from unittest import mock

from liberapay.billing.payday import create_payday_issue, main, NoPayday, Payday
from liberapay.billing.transactions import create_debt
from liberapay.i18n.currencies import MoneyBasket
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.testing import EUR, JPY, USD, Foobar
from liberapay.testing.mangopay import FakeTransfersHarness, MangopayHarness
from liberapay.testing.emails import EmailHarness


class TestPayday(EmailHarness, FakeTransfersHarness, MangopayHarness):

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

    def test_payday_moves_money(self):
        self.janet.set_tip_to(self.homer, EUR('6.00'))  # under $10!
        self.make_exchange('mango-cc', 10, 0, self.janet)
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert homer.balance == EUR('6.00')
        assert janet.balance == EUR('4.00')

        assert self.transfer_mock.call_count

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
             WHERE p.id = t.tippee
               AND p.mangopay_user_id IS NOT NULL;
            UPDATE participants
               SET giving = (10000,'EUR')
                 , taking = (10000,'EUR')
             WHERE mangopay_user_id IS NOT NULL;
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

    def test_update_cached_amounts_depth(self):
        # This test is currently broken, but we may be able to fix it someday
        return

        alice = self.make_participant('alice', balance=EUR(100))
        usernames = ('bob', 'carl', 'dana', 'emma', 'fred', 'greg')
        users = [self.make_participant(username) for username in usernames]

        prev = alice
        for user in reversed(users):
            prev.set_tip_to(user, EUR('1.00'))
            prev = user

        def check():
            for username in reversed(usernames[1:]):
                user = Participant.from_username(username)
                assert user.giving == EUR('1.00')
                assert user.receiving == EUR('1.00')
                assert user.npatrons == 1
            funded_tips = self.db.all("SELECT id FROM tips WHERE is_funded ORDER BY id")
            assert len(funded_tips) == 6

        check()
        Payday.start().update_cached_amounts()
        check()

    def test_prepare(self):
        self.clear_tables()
        self.make_participant('carl', balance=EUR(10))

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

    @staticmethod
    def get_new_balances(cursor):
        return {
            username: [m for m in balances if m.amount]
            for username, balances in cursor.all(
                "SELECT username, balances FROM payday_participants"
            )
        }

    def test_payday_doesnt_process_tips_when_goal_is_negative(self):
        self.make_exchange('mango-cc', 20, 0, self.janet)
        self.janet.set_tip_to(self.homer, EUR('13.00'))
        self.db.run("UPDATE participants SET goal = (-1,null) WHERE username='homer'")
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_virtually(cursor, payday.ts_start)
            new_balances = self.get_new_balances(cursor)
            assert new_balances == {
                'david': [],
                'homer': [],
                'janet': [EUR(20)],
            }

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
        self.make_exchange('mango-cc', 1, 0, self.david)
        self.david.set_tip_to(self.janet, EUR('0.51'))
        self.david.set_tip_to(self.homer, EUR('0.50'))
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_virtually(cursor, payday.ts_start)
            new_balances = self.get_new_balances(cursor)
            assert new_balances == {
                'david': [],
                'homer': [EUR('0.49')],
                'janet': [EUR('0.51')],
            }
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

    def test_transfer_tips_whole_graph(self):
        alice = self.make_participant('alice', balance=EUR(50))
        alice.set_tip_to(self.homer, EUR('50'))
        self.homer.set_tip_to(self.janet, EUR('20'))
        self.janet.set_tip_to(self.david, EUR('5'))
        self.david.set_tip_to(self.homer, EUR('20'))  # Partially funded

        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_virtually(cursor, payday.ts_start)
            new_balances = self.get_new_balances(cursor)
            assert new_balances == {
                'alice': [],
                'david': [],
                'homer': [EUR('35')],
                'janet': [EUR('15')],
            }

    def test_payday_handles_paid_in_advance(self):
        self.add_payment_account(self.david, 'stripe')
        self.add_payment_account(self.homer, 'paypal')
        self.make_exchange('mango-cc', EUR('2.00'), 0, self.janet)
        self.janet.set_tip_to(self.david, EUR('0.60'))
        team = self.make_participant('team', kind='group')
        team.set_take_for(self.homer, EUR('0.40'), team)
        self.janet.set_tip_to(team, EUR('0.40'))
        self.janet.distribute_balances_to_donees()

        # Preliminary checks
        janet = self.janet.refetch()
        assert janet.balance == 0
        tips = self.db.all("""
            SELECT *
              FROM current_tips
             WHERE tipper = %s
          ORDER BY id
        """, (janet.id,))
        assert len(tips) == 2
        assert tips[0].paid_in_advance == EUR('1.20')
        assert tips[1].paid_in_advance == EUR('0.80')
        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 2
        assert transfers[0].amount == EUR('1.20')
        assert transfers[0].context == 'tip-in-advance'
        assert transfers[1].amount == EUR('0.80')
        assert transfers[1].context == 'take-in-advance'

        # Now run a payday and check the results
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
        """, (janet.id,))
        assert len(tips) == 2
        assert tips[0].paid_in_advance == EUR('0.60')
        assert tips[1].paid_in_advance == EUR('0.40')
        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 4

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
        """, (janet.id,))
        assert len(tips) == 2
        assert not tips[0].paid_in_advance
        assert not tips[1].paid_in_advance
        transfers = self.db.all("SELECT * FROM transfers ORDER BY id")
        assert len(transfers) == 6

        emails = self.get_emails()
        assert len(emails) == 2
        assert emails[0]['to'][0] == 'david <%s>' % self.david.email
        assert '0.60' in emails[0]['subject']
        assert emails[1]['to'][0] == 'homer <%s>' % self.homer.email
        assert '0.40' in emails[1]['text']


class TestPaydayForTeams(FakeTransfersHarness):

    def test_transfer_takes(self):
        a_team = self.make_participant('a_team', kind='group')
        alice = self.make_participant('alice')
        a_team.set_take_for(alice, EUR('1.00'), a_team)
        bob = self.make_participant('bob')
        a_team.set_take_for(bob, EUR('0.01'), a_team)
        charlie = self.make_participant('charlie', balance=EUR(1000))
        charlie.set_tip_to(a_team, EUR('1.01'))

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

        participants = self.db.all("SELECT username, balance FROM participants")

        for p in participants:
            if p.username == 'alice':
                assert p.balance == EUR('1.00')
            elif p.username == 'bob':
                assert p.balance == EUR('0.01')
            elif p.username == 'charlie':
                assert p.balance == EUR('998.99')
            else:
                assert p.balance == 0

    def test_underfunded_team(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        team.set_take_for(alice, EUR('1.00'), team)
        bob = self.make_participant('bob')
        team.set_take_for(bob, EUR('1.00'), team)
        charlie = self.make_participant('charlie', balance=EUR(1000))
        charlie.set_tip_to(team, EUR('0.26'))

        Payday.start().run()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.13'),
            'bob': EUR('0.13'),
            'charlie': EUR('999.74'),
            'team': EUR('0.00'),
        }
        assert d == expected

    def test_non_divisible_team_income(self):
        """
        This tests the payment to teams with a nondivisible income (with respect to the number of team members):
            - creates a team of 7 people
            - has a total income of 0.85 euros/week
            - each member of the team would like to have an income of 1 euro
            - each participant will 0.12 euros except 1 participant will have 0.13 euross
            - team should have a leftover of 0.00 euros after each week
        """
        team = self.make_participant('team', kind='group')
        charlie = self.make_participant('charlie', balance=EUR(1000))
        charlie.set_tip_to(team, EUR('0.85'))

        jillian = self.make_participant('jillian')
        marisa = self.make_participant('marisa')
        kevin = self.make_participant('kevin')
        brandon = self.make_participant('brandon')
        rachel = self.make_participant('rachel')
        linda = self.make_participant('linda')
        raymond = self.make_participant('raymond')

        team.set_take_for(jillian, EUR('1.00'), team)
        team.set_take_for(marisa, EUR('1.00'), team)
        team.set_take_for(kevin, EUR('1.00'), team)
        team.set_take_for(brandon, EUR('1.00'), team)
        team.set_take_for(rachel, EUR('1.00'), team)
        team.set_take_for(linda, EUR('1.00'), team)
        team.set_take_for(raymond, EUR('1.00'), team)

        Payday.start().run()

        count_twelve = 0
        count_thirteen = 0
        count_team = 0

        for check in self.db.all("SELECT username, balance FROM participants"):
            if check.balance == EUR('0.12'):
                count_twelve += 1
            elif check.balance == EUR('0.13'):
                count_thirteen += 1
            elif check.username == 'team' and check.balance == EUR('0.00'):
                count_team += 1

        assert count_twelve == 6
        assert count_thirteen == 1
        assert count_team == 1


    def test_wellfunded_team(self):
        """
        This tests two properties:
        - takes are maximums
        - donors all pay their share, the first donor doesn't pay everything
        """
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        team.set_take_for(alice, EUR('0.79'), team)
        bob = self.make_participant('bob')
        team.set_take_for(bob, EUR('0.21'), team)
        charlie = self.make_participant('charlie', balance=EUR(10))
        charlie.set_tip_to(team, EUR('5.00'))
        dan = self.make_participant('dan', balance=EUR(10))
        dan.set_tip_to(team, EUR('5.00'))

        Payday.start().run()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.79'),
            'bob': EUR('0.21'),
            'charlie': EUR('9.5'),
            'dan': EUR('9.5'),
            'team': EUR('0.00'),
        }
        assert d == expected

    def test_wellfunded_team_with_early_donor(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        team.set_take_for(alice, EUR('0.79'), team)
        bob = self.make_participant('bob')
        team.set_take_for(bob, EUR('0.21'), team)
        charlie = self.make_participant('charlie', balance=EUR(10))
        charlie.set_tip_to(team, EUR('2.00'))

        print("> Step 1: three weeks of donations from charlie only")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.79') * 3,
            'bob': EUR('0.21') * 3,
            'charlie': EUR('7.00'),
            'team': EUR('0.00'),
        }
        assert d == expected

        print("> Step 2: dan joins the party, charlie's donation is automatically "
              "reduced while dan catches up")
        print()
        dan = self.make_participant('dan', balance=EUR(10))
        dan.set_tip_to(team, EUR('2.00'))

        for i in range(6):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.79') * 9,
            'bob': EUR('0.21') * 9,
            'charlie': EUR('5.50'),
            'dan': EUR('5.50'),
            'team': EUR('0.00'),
        }
        assert d == expected

        print("> Step 3: dan has caught up with charlie, they will now both give 0.50")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.79') * 12,
            'bob': EUR('0.21') * 12,
            'charlie': EUR('4.00'),
            'dan': EUR('4.00'),
            'team': EUR('0.00'),
        }
        assert d == expected

    def test_wellfunded_team_with_two_early_donors(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        team.set_take_for(alice, EUR('0.79'), team)
        bob = self.make_participant('bob')
        team.set_take_for(bob, EUR('0.21'), team)
        charlie = self.make_participant('charlie', balance=EUR(10))
        charlie.set_tip_to(team, EUR('1.00'))
        dan = self.make_participant('dan', balance=EUR(10))
        dan.set_tip_to(team, EUR('3.00'))

        print("> Step 1: three weeks of donations from early donors")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.79') * 3,
            'bob': EUR('0.21') * 3,
            'charlie': EUR('9.25'),
            'dan': EUR('7.75'),
            'team': EUR('0.00'),
        }
        assert d == expected

        print("> Step 2: a new donor appears, the contributions of the early "
              "donors automatically decrease while the new donor catches up")
        print()
        emma = self.make_participant('emma', balance=EUR(10))
        emma.set_tip_to(team, EUR('1.00'))

        Payday.start().run(recompute_stats=0, update_cached_amounts=False)
        print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.79') * 4,
            'bob': EUR('0.21') * 4,
            'charlie': EUR('9.19'),
            'dan': EUR('7.59'),
            'emma': EUR('9.22'),
            'team': EUR('0.00'),
        }
        assert d == expected

        Payday.start().run(recompute_stats=0, update_cached_amounts=False)
        print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.79') * 5,
            'bob': EUR('0.21') * 5,
            'charlie': EUR('8.99'),
            'dan': EUR('7.01'),
            'emma': EUR('9.00'),
            'team': EUR('0.00'),
        }
        assert d == expected

        print("> Step 3: emma has caught up with the early donors")
        print()

        for i in range(2):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.79') * 7,
            'bob': EUR('0.21') * 7,
            'charlie': EUR('8.60'),
            'dan': EUR('5.80'),
            'emma': EUR('8.60'),
            'team': EUR('0.00'),
        }
        assert d == expected

    def test_wellfunded_team_with_two_early_donors_and_low_amounts(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        team.set_take_for(alice, EUR('0.01'), team)
        bob = self.make_participant('bob')
        team.set_take_for(bob, EUR('0.01'), team)
        charlie = self.make_participant('charlie', balance=EUR(10))
        charlie.set_tip_to(team, EUR('0.02'))
        dan = self.make_participant('dan', balance=EUR(10))
        dan.set_tip_to(team, EUR('0.02'))

        print("> Step 1: three weeks of donations from early donors")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.01') * 3,
            'bob': EUR('0.01') * 3,
            'charlie': EUR('9.97'),
            'dan': EUR('9.97'),
            'team': EUR('0.00'),
        }
        assert d == expected

        print("> Step 2: a new donor appears, the contributions of the early "
              "donors automatically decrease while the new donor catches up")
        print()
        emma = self.make_participant('emma', balance=EUR(10))
        emma.set_tip_to(team, EUR('0.02'))

        for i in range(6):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.01') * 9,
            'bob': EUR('0.01') * 9,
            'charlie': EUR('9.94'),
            'dan': EUR('9.94'),
            'emma': EUR('9.94'),
            'team': EUR('0.00'),
        }
        assert d == expected

    def test_wellfunded_team_with_early_donor_and_small_leftover(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        team.set_take_for(alice, EUR('0.50'), team)
        bob = self.make_participant('bob')
        team.set_take_for(bob, EUR('0.50'), team)
        charlie = self.make_participant('charlie', balance=EUR(10))
        charlie.set_tip_to(team, EUR('0.52'))

        print("> Step 1: three weeks of donations from early donor")
        print()
        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.26') * 3,
            'bob': EUR('0.26') * 3,
            'charlie': EUR('8.44'),
            'team': EUR('0.00'),
        }
        assert d == expected

        print("> Step 2: a new donor appears, the contribution of the early "
              "donor automatically decreases while the new donor catches up, "
              "but the leftover is small so the adjustments are limited")
        print()
        dan = self.make_participant('dan', balance=EUR(10))
        dan.set_tip_to(team, EUR('0.52'))

        for i in range(3):
            Payday.start().run(recompute_stats=0, update_cached_amounts=False)
            print()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.26') * 3 + EUR('0.50') * 3,
            'bob': EUR('0.26') * 3 + EUR('0.50') * 3,
            'charlie': EUR('7.00'),
            'dan': EUR('8.44'),
            'team': EUR('0.00'),
        }
        assert d == expected

    def test_mutual_tipping_through_teams(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice', balance=EUR(8))
        alice.set_tip_to(team, EUR('2.00'))
        team.set_take_for(alice, EUR('0.25'), team)
        bob = self.make_participant('bob', balance=EUR(10))
        bob.set_tip_to(team, EUR('2.00'))
        team.set_take_for(bob, EUR('0.75'), team)

        Payday.start().run()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('7.75'),  # 8 - 0.50 + 0.25
            'bob': EUR('10.25'),  # 10 - 0.25 + 0.50
            'team': EUR('0.00'),
        }
        assert d == expected

    def test_unfunded_tip_to_team_doesnt_cause_NegativeBalance(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        alice.set_tip_to(team, EUR('1.00'))  # unfunded tip
        bob = self.make_participant('bob')
        team.set_take_for(bob, EUR('1.00'), team)

        Payday.start().run()

        d = dict(self.db.all("SELECT username, balance FROM participants"))
        expected = {
            'alice': EUR('0.00'),
            'bob': EUR('0.00'),
            'team': EUR('0.00'),
        }
        assert d == expected

    # Two currencies
    # ==============

    def set_up_team_with_two_currencies(self):
        team = self.team = self.make_participant(
            'team', kind='group', accepted_currencies='EUR,USD'
        )
        self.alice = self.make_participant('alice', main_currency='EUR',
                                           accepted_currencies='EUR,USD')
        team.set_take_for(self.alice, EUR('1.00'), team)
        self.bob = self.make_participant('bob', main_currency='USD',
                                         accepted_currencies='EUR,USD')
        team.set_take_for(self.bob, EUR('1.00'), team)
        self.donor1_eur = self.make_participant('donor1_eur', balance=EUR(100))
        self.donor2_usd = self.make_participant('donor2_usd', balance=USD(100))
        self.donor3_eur = self.make_participant('donor3_eur', balance=EUR(100))
        self.donor4_usd = self.make_participant('donor4_usd', balance=USD(100))

    def test_transfer_takes_with_two_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('0.50'))
        self.donor2_usd.set_tip_to(self.team, USD('0.60'))
        self.donor3_eur.set_tip_to(self.team, EUR('0.50'))
        self.donor4_usd.set_tip_to(self.team, USD('0.60'))

        Payday.start().shuffle()

        expected = {
            'alice': MoneyBasket(EUR('1.00')),
            'bob': MoneyBasket(USD('1.20')),
            'donor1_eur': MoneyBasket(EUR('99.50')),
            'donor2_usd': MoneyBasket(USD('99.40')),
            'donor3_eur': MoneyBasket(EUR('99.50')),
            'donor4_usd': MoneyBasket(USD('99.40')),
        }
        actual = self.get_balances()
        assert expected == actual

    def test_transfer_takes_with_two_currencies_on_both_sides(self):
        self.set_up_team_with_two_currencies()
        self.team.set_take_for(self.alice, USD('0.01'), self.alice)
        self.team.set_take_for(self.bob, EUR('0.01'), self.bob)
        self.donor1_eur.set_tip_to(self.team, EUR('0.01'))
        self.donor2_usd.set_tip_to(self.team, USD('0.01'))

        Payday.start().shuffle()

        expected = {
            'alice': MoneyBasket(EUR('0.01')),
            'bob': MoneyBasket(USD('0.01')),
            'donor1_eur': MoneyBasket(EUR('99.99')),
            'donor2_usd': MoneyBasket(USD('99.99')),
            'donor3_eur': MoneyBasket(EUR('100')),
            'donor4_usd': MoneyBasket(USD('100')),
        }
        actual = self.get_balances()
        assert expected == actual

    def test_wellfunded_team_with_two_balanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('1.00'))
        self.donor2_usd.set_tip_to(self.team, USD('1.20'))
        self.donor3_eur.set_tip_to(self.team, EUR('1.00'))
        self.donor4_usd.set_tip_to(self.team, USD('1.20'))

        Payday.start().shuffle()

        expected = {
            'alice': MoneyBasket(EUR('1.00')),
            'bob': MoneyBasket(USD('1.20')),
            'donor1_eur': MoneyBasket(EUR('99.50')),
            'donor2_usd': MoneyBasket(USD('99.40')),
            'donor3_eur': MoneyBasket(EUR('99.50')),
            'donor4_usd': MoneyBasket(USD('99.40')),
        }
        actual = self.get_balances()
        assert expected == actual

    def test_exactly_funded_team_with_two_unbalanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('0.75'))
        self.donor2_usd.set_tip_to(self.team, USD('0.30'))
        self.donor3_eur.set_tip_to(self.team, EUR('0.75'))
        self.donor4_usd.set_tip_to(self.team, USD('0.30'))

        Payday.start().shuffle()

        expected = {
            'alice': MoneyBasket(EUR('1.00')),
            'bob': MoneyBasket(EUR('0.50'), USD('0.60')),
            'donor1_eur': MoneyBasket(EUR('99.25')),
            'donor2_usd': MoneyBasket(USD('99.70')),
            'donor3_eur': MoneyBasket(EUR('99.25')),
            'donor4_usd': MoneyBasket(USD('99.70')),
        }
        actual = self.get_balances()
        assert expected == actual

    def test_wellfunded_team_with_two_unbalanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('1.50'))
        self.donor2_usd.set_tip_to(self.team, USD('0.60'))
        self.donor3_eur.set_tip_to(self.team, EUR('1.50'))
        self.donor4_usd.set_tip_to(self.team, USD('0.60'))

        Payday.start().shuffle()

        expected = {
            'alice': MoneyBasket(EUR('1.00')),
            'bob': MoneyBasket(EUR('0.50'), USD('0.60')),
            'donor1_eur': MoneyBasket(EUR('99.25')),
            'donor2_usd': MoneyBasket(USD('99.70')),
            'donor3_eur': MoneyBasket(EUR('99.25')),
            'donor4_usd': MoneyBasket(USD('99.70')),
        }
        actual = self.get_balances()
        assert expected == actual

    def test_underfunded_team_with_two_balanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('0.25'))
        self.donor2_usd.set_tip_to(self.team, USD('0.30'))
        self.donor3_eur.set_tip_to(self.team, EUR('0.25'))
        self.donor4_usd.set_tip_to(self.team, USD('0.30'))

        Payday.start().shuffle()

        expected = {
            'alice': MoneyBasket(EUR('0.50')),
            'bob': MoneyBasket(USD('0.60')),
            'donor1_eur': MoneyBasket(EUR('99.75')),
            'donor2_usd': MoneyBasket(USD('99.70')),
            'donor3_eur': MoneyBasket(EUR('99.75')),
            'donor4_usd': MoneyBasket(USD('99.70')),
        }
        actual = self.get_balances()
        assert expected == actual

    def test_underfunded_team_with_two_unbalanced_currencies(self):
        self.set_up_team_with_two_currencies()
        self.donor1_eur.set_tip_to(self.team, EUR('0.10'))
        self.donor2_usd.set_tip_to(self.team, USD('0.25'))
        self.donor3_eur.set_tip_to(self.team, EUR('0.10'))
        self.donor4_usd.set_tip_to(self.team, USD('0.25'))

        Payday.start().shuffle()

        expected = {
            'alice': MoneyBasket(EUR('0.20'), USD('0.13')),
            'bob': MoneyBasket(USD('0.37')),
            'donor1_eur': MoneyBasket(EUR('99.90')),
            'donor2_usd': MoneyBasket(USD('99.75')),
            'donor3_eur': MoneyBasket(EUR('99.90')),
            'donor4_usd': MoneyBasket(USD('99.75')),
        }
        actual = self.get_balances()
        assert expected == actual

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

        carl_card = ExchangeRoute.insert(
            carl, 'stripe-card', 'x', 'chargeable', remote_user_id='x'
        )
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

        donor_card = ExchangeRoute.insert(
            donor, 'stripe-card', 'x', 'chargeable', remote_user_id='x'
        )
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

        carl_card = ExchangeRoute.insert(
            carl, 'stripe-card', 'x', 'chargeable', remote_user_id='x'
        )
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

        carl_card = ExchangeRoute.insert(
            carl, 'stripe-card', 'x', 'chargeable', remote_user_id='x'
        )
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


class TestPayday2(EmailHarness, FakeTransfersHarness, MangopayHarness):

    def test_it_handles_invoices_correctly(self):
        org = self.make_participant('org', kind='organization', allow_invoices=True)
        self.make_exchange('mango-cc', 60, 0, self.janet)
        self.janet.set_tip_to(org, EUR('50.00'))
        self.db.run("UPDATE participants SET allow_invoices = true WHERE id = %s",
                    (self.janet.id,))
        self.make_invoice(self.janet, org, EUR('40.02'), 'accepted')
        self.make_invoice(self.janet, org, EUR('80.04'), 'accepted')
        self.make_invoice(self.janet, org, EUR('5.16'), 'rejected')
        self.make_invoice(self.janet, org, EUR('3.77'), 'new')
        self.make_invoice(self.janet, org, EUR('1.23'), 'pre')
        Payday.start().run()
        expense_transfers = self.db.all("SELECT * FROM transfers WHERE context = 'expense'")
        assert len(expense_transfers) == 1
        d = dict(self.db.all("SELECT username, balance FROM participants WHERE balance <> 0"))
        assert d == {
            'org': EUR('9.98'),
            'janet': EUR('50.02'),
        }

    def test_payday_tries_to_settle_debts(self):
        # First, test a small debt which can be settled
        e1_id = self.make_exchange('mango-cc', 10, 0, self.janet)
        debt = create_debt(self.db, self.janet.id, self.homer.id, EUR(5), e1_id)
        e2_id = self.make_exchange('mango-cc', 20, 0, self.janet)
        Payday.start().run()
        balances = dict(self.db.all("SELECT username, balance FROM participants"))
        assert balances == {
            'janet': 25,
            'homer': 5,
            'david': 0,
        }
        debt = self.db.one("SELECT * FROM debts WHERE id = %s", (debt.id,))
        assert debt.status == 'paid'
        # Second, test a big debt that can't be settled
        self.make_exchange('mango-ba', -15, 0, self.janet)
        debt2 = create_debt(self.db, self.janet.id, self.homer.id, EUR(20), e2_id)
        Payday.start().run()
        balances = dict(self.db.all("SELECT username, balance FROM participants"))
        assert balances == {
            'janet': 10,
            'homer': 5,
            'david': 0,
        }
        debt2 = self.db.one("SELECT * FROM debts WHERE id = %s", (debt2.id,))
        assert debt2.status == 'due'

    def test_it_notifies_participants(self):
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
        self.client.PxST('/homer/emails/', auth_as=self.homer,
                         data={'events': 'income', 'income': ''}, xhr=True)
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
