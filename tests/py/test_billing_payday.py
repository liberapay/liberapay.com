from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D
import os

import mock

from liberapay.billing.payday import NoPayday, Payday
from liberapay.exceptions import NegativeBalance
from liberapay.models.participant import Participant
from liberapay.testing.mangopay import FakeTransfersHarness, MangopayHarness
from liberapay.testing.emails import EmailHarness


class TestPayday(EmailHarness, FakeTransfersHarness, MangopayHarness):

    def test_payday_moves_money(self):
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        self.make_exchange('mango-cc', 10, 0, self.janet)
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert homer.balance == D('6.00')
        assert janet.balance == D('4.00')

        assert self.transfer_mock.call_count

    def test_payday_doesnt_move_money_from_a_suspicious_account(self):
        self.db.run("""
            UPDATE participants
               SET is_suspicious = true
             WHERE username = 'janet'
        """)
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert janet.balance == D('0.00')
        assert homer.balance == D('0.00')

    def test_payday_doesnt_move_money_to_a_suspicious_account(self):
        self.db.run("""
            UPDATE participants
               SET is_suspicious = true
             WHERE username = 'homer'
        """)
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert janet.balance == D('0.00')
        assert homer.balance == D('0.00')

    def test_update_cached_amounts(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')
        carl = self.make_participant('carl', balance=1.56)
        dana = self.make_participant('dana')
        emma = Participant.make_stub(username='emma')
        alice.set_tip_to(dana, '3.00')
        alice.set_tip_to(bob, '6.00')
        alice.set_tip_to(emma, '0.50')
        alice.set_tip_to(team, '1.00')
        bob.set_tip_to(alice, '5.00')
        team.add_member(bob)
        team.set_take_for(bob, D('1.00'), bob)
        bob.set_tip_to(dana, '2.00')  # funded by bob's take
        bob.set_tip_to(emma, '7.00')  # not funded, insufficient receiving
        carl.set_tip_to(dana, '2.08')  # not funded, insufficient balance

        def check():
            alice = Participant.from_username('alice')
            bob = Participant.from_username('bob')
            carl = Participant.from_username('carl')
            dana = Participant.from_username('dana')
            emma = Participant.from_username('emma')
            assert alice.giving == D('10.00')
            assert alice.receiving == D('5.00')
            assert bob.giving == D('7.00')
            assert bob.receiving == D('7.00')
            assert bob.taking == D('1.00')
            assert carl.giving == D('0.00')
            assert carl.receiving == D('0.00')
            assert dana.receiving == D('5.00')
            assert dana.npatrons == 2
            assert emma.receiving == D('0.50')
            assert emma.npatrons == 1
            funded_tips = self.db.all("SELECT amount FROM tips WHERE is_funded ORDER BY id")
            assert funded_tips == [3, 6, 0.5, 1, 5, 2]

        # Pre-test check
        check()

        # Check that update_cached_amounts doesn't mess anything up
        Payday.start().update_cached_amounts()
        check()

        # Check that update_cached_amounts actually updates amounts
        self.db.run("""
            UPDATE tips t
               SET is_funded = false
              FROM participants p
             WHERE p.id = t.tippee
               AND p.mangopay_user_id IS NOT NULL;
            UPDATE participants
               SET giving = 0
                 , npatrons = 0
                 , receiving = 0
                 , taking = 0
             WHERE mangopay_user_id IS NOT NULL;
        """)
        Payday.start().update_cached_amounts()
        check()

    def test_update_cached_amounts_depth(self):
        alice = self.make_participant('alice', balance=100)
        usernames = ('bob', 'carl', 'dana', 'emma', 'fred', 'greg')
        users = [self.make_participant(username) for username in usernames]

        prev = alice
        for user in reversed(users):
            prev.set_tip_to(user, '1.00')
            prev = user

        def check():
            for username in reversed(usernames[1:]):
                user = Participant.from_username(username)
                assert user.giving == D('1.00')
                assert user.receiving == D('1.00')
                assert user.npatrons == 1
            funded_tips = self.db.all("SELECT id FROM tips WHERE is_funded ORDER BY id")
            assert len(funded_tips) == 6

        check()
        Payday.start().update_cached_amounts()
        check()

    @mock.patch('liberapay.billing.payday.log')
    def test_start_prepare(self, log):
        self.clear_tables()
        self.make_participant('carl', balance=10)

        payday = Payday.start()
        ts_start = payday.ts_start

        get_participants = lambda c: c.all("SELECT * FROM payday_participants")

        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, ts_start)
            participants = get_participants(cursor)

        expected_logging_call_args = [
            ('Starting a new payday.'),
            ('Payday started at {}.'.format(ts_start)),
            ('Prepared the DB.'),
        ]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            assert args[0] == expected_logging_call_args.pop()

        log.reset_mock()

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

        expected_logging_call_args = [
            ('Picking up with an existing payday.'),
            ('Payday started at {}.'.format(second_ts_start)),
            ('Prepared the DB.'),
        ]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            assert args[0] == expected_logging_call_args.pop()

    def test_end(self):
        Payday.start().end()
        result = self.db.one("SELECT count(*) FROM paydays "
                             "WHERE ts_end > '1970-01-01'")
        assert result == 1

    def test_end_raises_NoPayday(self):
        with self.assertRaises(NoPayday):
            Payday().end()

    def test_payday_cant_make_balances_more_negative(self):
        self.db.run("""
            UPDATE participants SET balance = -10 WHERE username='janet'
        """)
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            cursor.run("""
                UPDATE payday_participants
                   SET new_balance = -50
                 WHERE username IN ('janet', 'homer')
            """)
            with self.assertRaises(NegativeBalance):
                payday.check_balances(cursor)

    @staticmethod
    def get_new_balances(cursor):
        return {id: new_balance for id, new_balance in cursor.all(
            "SELECT id, new_balance FROM payday_participants"
        )}

    def test_payday_doesnt_process_tips_when_goal_is_negative(self):
        self.make_exchange('mango-cc', 20, 0, self.janet)
        self.janet.set_tip_to(self.homer, 13)
        self.db.run("UPDATE participants SET goal = -1 WHERE username='homer'")
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_virtually(cursor)
            new_balances = self.get_new_balances(cursor)
            assert new_balances[self.janet.id] == 20
            assert new_balances[self.homer.id] == 0

    def test_payday_doesnt_make_null_transfers(self):
        alice = self.make_participant('alice')
        alice.set_tip_to(self.homer, 1)
        alice.set_tip_to(self.homer, 0)
        a_team = self.make_participant('a_team', kind='group')
        a_team.add_member(alice)
        Payday.start().run()
        transfers0 = self.db.all("SELECT * FROM transfers WHERE amount = 0")
        assert not transfers0

    def test_transfer_tips(self):
        self.make_exchange('mango-cc', 1, 0, self.david)
        self.david.set_tip_to(self.janet, D('0.51'))
        self.david.set_tip_to(self.homer, D('0.50'))
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_virtually(cursor)
            new_balances = self.get_new_balances(cursor)
            assert new_balances[self.david.id] == D('0.49')
            assert new_balances[self.janet.id] == D('0.51')
            assert new_balances[self.homer.id] == 0

    def test_transfer_tips_whole_graph(self):
        alice = self.make_participant('alice', balance=50)
        alice.set_tip_to(self.homer, D('50'))
        self.homer.set_tip_to(self.janet, D('20'))
        self.janet.set_tip_to(self.david, D('5'))
        self.david.set_tip_to(self.homer, D('20'))  # Should be unfunded

        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_virtually(cursor)
            new_balances = self.get_new_balances(cursor)
            assert new_balances[alice.id] == D('0')
            assert new_balances[self.homer.id] == D('30')
            assert new_balances[self.janet.id] == D('15')
            assert new_balances[self.david.id] == D('5')

    def test_transfer_takes(self):
        a_team = self.make_participant('a_team', kind='group')
        alice = self.make_participant('alice')
        a_team.set_take_for(alice, D('1.00'), alice)
        bob = self.make_participant('bob')
        a_team.set_take_for(bob, D('0.01'), bob)
        charlie = self.make_participant('charlie', balance=1000)
        charlie.set_tip_to(a_team, D('1.01'))

        payday = Payday.start()

        # Test that payday ignores takes set after it started
        a_team.set_take_for(alice, D('2.00'), alice)

        # Run the transfer multiple times to make sure we ignore takes that
        # have already been processed
        for i in range(3):
            payday.shuffle()

        os.unlink(payday.transfers_filename)

        participants = self.db.all("SELECT username, balance FROM participants")

        for p in participants:
            if p.username == 'alice':
                assert p.balance == D('1.00')
            elif p.username == 'bob':
                assert p.balance == D('0.01')
            elif p.username == 'charlie':
                assert p.balance == D('998.99')
            else:
                assert p.balance == 0

    def test_it_notifies_participants(self):
        self.make_exchange('mango-cc', 10, 0, self.janet)
        self.janet.set_tip_to(self.david, '4.50')
        self.janet.set_tip_to(self.homer, '3.50')
        self.client.POST('/homer/emails/notifications.json', auth_as=self.homer,
                         data={'fields': 'income', 'income': ''}, xhr=True)
        Payday.start().run()
        emails = self.get_emails()
        assert len(emails) == 2
        assert emails[0]['to'][0]['email'] == self.david.email
        assert '4.50' in emails[0]['subject']
        assert emails[1]['to'][0]['email'] == self.janet.email
        assert 'top up' in emails[1]['subject']
