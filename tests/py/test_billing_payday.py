from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D
import os

import balanced
import mock

from gratipay.billing.exchanges import create_card_hold
from gratipay.billing.payday import NoPayday, Payday
from gratipay.exceptions import NegativeBalance
from gratipay.models.participant import Participant
from gratipay.testing import Foobar, Harness
from gratipay.testing.balanced import BalancedHarness
from gratipay.testing.emails import EmailHarness


class TestPayday(BalancedHarness):

    @mock.patch.object(Payday, 'fetch_card_holds')
    def test_payday_moves_money(self, fch):
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        fch.return_value = {}
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert homer.balance == D('6.00')
        assert janet.balance == D('3.41')

    @mock.patch.object(Payday, 'fetch_card_holds')
    def test_payday_doesnt_move_money_from_a_suspicious_account(self, fch):
        self.db.run("""
            UPDATE participants
               SET is_suspicious = true
             WHERE username = 'janet'
        """)
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        fch.return_value = {}
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert janet.balance == D('0.00')
        assert homer.balance == D('0.00')

    @mock.patch.object(Payday, 'fetch_card_holds')
    def test_payday_doesnt_move_money_to_a_suspicious_account(self, fch):
        self.db.run("""
            UPDATE participants
               SET is_suspicious = true
             WHERE username = 'homer'
        """)
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        fch.return_value = {}
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert janet.balance == D('0.00')
        assert homer.balance == D('0.00')

    @mock.patch.object(Payday, 'fetch_card_holds')
    def test_payday_moves_money_with_balanced(self, fch):
        self.janet.set_tip_to(self.homer, '15.00')
        fch.return_value = {}
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert janet.balance == D('0.00')
        assert homer.balance == D('0.00')

        janet_customer = balanced.Customer.fetch(janet.balanced_customer_href)
        homer_customer = balanced.Customer.fetch(homer.balanced_customer_href)

        created_at = balanced.Transaction.f.created_at

        credit = homer_customer.credits.sort(created_at.desc()).first()
        assert credit.amount == 1500
        assert credit.description == 'homer'

        debit = janet_customer.debits.sort(created_at.desc()).first()
        assert debit.amount == 1576  # base amount + fee
        assert debit.description == 'janet'

    @mock.patch.object(Payday, 'fetch_card_holds')
    @mock.patch('gratipay.billing.payday.create_card_hold')
    def test_ncc_failing(self, cch, fch):
        self.janet.set_tip_to(self.homer, 24)
        fch.return_value = {}
        cch.return_value = (None, 'oops')
        payday = Payday.start()
        before = self.fetch_payday()
        assert before['ncc_failing'] == 0
        payday.payin()
        after = self.fetch_payday()
        assert after['ncc_failing'] == 1

    def test_update_cached_amounts(self):
        team = self.make_participant('team', claimed_time='now', number='plural')
        alice = self.make_participant('alice', claimed_time='now', last_bill_result='')
        bob = self.make_participant('bob', claimed_time='now')
        carl = self.make_participant('carl', claimed_time='now', last_bill_result="Fail!")
        dana = self.make_participant('dana', claimed_time='now')
        emma = self.make_participant('emma')
        alice.set_tip_to(dana, '3.00')
        alice.set_tip_to(bob, '6.00')
        alice.set_tip_to(emma, '1.00')
        alice.set_tip_to(team, '4.00')
        bob.set_tip_to(alice, '5.00')
        team.add_member(bob)
        team.set_take_for(bob, D('1.00'), bob)
        bob.set_tip_to(dana, '2.00')  # funded by bob's take
        bob.set_tip_to(emma, '7.00')  # not funded, insufficient receiving
        carl.set_tip_to(dana, '2.08')  # not funded, failing card

        def check():
            alice = Participant.from_username('alice')
            bob = Participant.from_username('bob')
            carl = Participant.from_username('carl')
            dana = Participant.from_username('dana')
            emma = Participant.from_username('emma')
            assert alice.giving == D('13.00')
            assert alice.pledging == D('1.00')
            assert alice.receiving == D('5.00')
            assert bob.giving == D('7.00')
            assert bob.receiving == D('7.00')
            assert bob.taking == D('1.00')
            assert carl.giving == D('0.00')
            assert carl.receiving == D('0.00')
            assert dana.receiving == D('5.00')
            assert dana.npatrons == 2
            assert emma.receiving == D('1.00')
            assert emma.npatrons == 1
            funded_tips = self.db.all("SELECT amount FROM tips WHERE is_funded ORDER BY id")
            assert funded_tips == [3, 6, 1, 4, 5, 2]

        # Pre-test check
        check()

        # Check that update_cached_amounts doesn't mess anything up
        Payday.start().update_cached_amounts()
        check()

        # Check that update_cached_amounts actually updates amounts
        self.db.run("""
            UPDATE tips SET is_funded = false;
            UPDATE participants
               SET giving = 0
                 , npatrons = 0
                 , pledging = 0
                 , receiving = 0
                 , taking = 0;
        """)
        Payday.start().update_cached_amounts()
        check()

    def test_update_cached_amounts_depth(self):
        alice = self.make_participant('alice', claimed_time='now', last_bill_result='')
        usernames = ('bob', 'carl', 'dana', 'emma', 'fred', 'greg')
        users = [self.make_participant(username, claimed_time='now') for username in usernames]

        prev = alice
        for user in reversed(users):
            prev.set_tip_to(user, '1.00')
            prev = user

        def check():
            for username in reversed(usernames[1:]):
                user = Participant.from_username(username)
                assert user.giving == D('1.00')
                assert user.pledging == D('0.00')
                assert user.receiving == D('1.00')
                assert user.npatrons == 1
            funded_tips = self.db.all("SELECT id FROM tips WHERE is_funded ORDER BY id")
            assert len(funded_tips) == 6

        check()
        Payday.start().update_cached_amounts()
        check()

    @mock.patch('gratipay.billing.payday.log')
    def test_start_prepare(self, log):
        self.clear_tables()
        self.make_participant('bob', balance=10, claimed_time=None)
        self.make_participant('carl', balance=10, claimed_time='now')

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

        # carl is the only valid participant as he has a claimed time
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

    @mock.patch('gratipay.billing.payday.log')
    @mock.patch('gratipay.billing.payday.Payday.payin')
    def test_payday(self, payin, log):
        greeting = 'Greetings, program! It\'s PAYDAY!!!!'
        Payday.start().run()
        log.assert_any_call(greeting)
        assert payin.call_count == 1


class TestPayin(BalancedHarness):

    def create_card_holds(self):
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            return payday.create_card_holds(cursor)

    @mock.patch.object(Payday, 'fetch_card_holds')
    @mock.patch('gratipay.billing.payday.create_card_hold')
    def test_hold_amount_includes_negative_balance(self, cch, fch):
        self.db.run("""
            UPDATE participants SET balance = -10 WHERE username='janet'
        """)
        self.janet.set_tip_to(self.homer, 25)
        fch.return_value = {}
        cch.return_value = (None, 'some error')
        self.create_card_holds()
        assert cch.call_args[0][-1] == 35

    def test_payin_fetches_and_uses_existing_holds(self):
        self.janet.set_tip_to(self.homer, 20)
        hold, error = create_card_hold(self.db, self.janet, D(20))
        assert hold is not None
        assert not error
        with mock.patch('gratipay.billing.payday.create_card_hold') as cch:
            cch.return_value = (None, None)
            self.create_card_holds()
            assert not cch.called, cch.call_args_list

    @mock.patch.object(Payday, 'fetch_card_holds')
    def test_payin_cancels_existing_holds_of_insufficient_amounts(self, fch):
        self.janet.set_tip_to(self.homer, 30)
        hold, error = create_card_hold(self.db, self.janet, D(10))
        assert not error
        fch.return_value = {self.janet.id: hold}
        with mock.patch('gratipay.billing.payday.create_card_hold') as cch:
            fake_hold = object()
            cch.return_value = (fake_hold, None)
            holds = self.create_card_holds()
            assert len(holds) == 1
            assert holds[self.janet.id] is fake_hold
            assert hold.voided_at is not None

    @mock.patch('gratipay.billing.payday.CardHold')
    @mock.patch('gratipay.billing.payday.cancel_card_hold')
    def test_fetch_card_holds_handles_extra_holds(self, cancel, CardHold):
        fake_hold = mock.MagicMock()
        fake_hold.meta = {'participant_id': 0}
        fake_hold.save = mock.MagicMock()
        CardHold.query.filter.return_value = [fake_hold]
        for attr, state in (('failure_reason', 'failed'),
                            ('voided_at', 'cancelled'),
                            ('debit_href', 'captured')):
            holds = Payday.fetch_card_holds(set())
            assert fake_hold.meta['state'] == state
            fake_hold.save.assert_called_with()
            assert len(holds) == 0
            setattr(fake_hold, attr, None)
        holds = Payday.fetch_card_holds(set())
        cancel.assert_called_with(fake_hold)
        assert len(holds) == 0

    @mock.patch('gratipay.billing.payday.log')
    def test_payin_cancels_uncaptured_holds(self, log):
        self.janet.set_tip_to(self.homer, 42)
        alice = self.make_participant('alice', claimed_time='now',
                                      is_suspicious=False)
        self.make_exchange('balanced-cc', 50, 0, alice)
        alice.set_tip_to(self.janet, 50)
        Payday.start().payin()
        assert log.call_args_list[-3][0] == ("Captured 0 card holds.",)
        assert log.call_args_list[-2][0] == ("Canceled 1 card holds.",)
        assert Participant.from_id(alice.id).balance == 0
        assert Participant.from_id(self.janet.id).balance == 8
        assert Participant.from_id(self.homer.id).balance == 42

    def test_payin_cant_make_balances_more_negative(self):
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
                payday.update_balances(cursor)

    @mock.patch.object(Payday, 'fetch_card_holds')
    @mock.patch('gratipay.billing.exchanges.thing_from_href')
    def test_card_hold_error(self, tfh, fch):
        self.janet.set_tip_to(self.homer, 17)
        tfh.side_effect = Foobar
        fch.return_value = {}
        Payday.start().payin()
        payday = self.fetch_payday()
        assert payday['ncc_failing'] == 1

    def test_payin_doesnt_process_tips_when_goal_is_negative(self):
        alice = self.make_participant('alice', claimed_time='now', balance=20)
        bob = self.make_participant('bob', claimed_time='now')
        alice.set_tip_to(bob, 13)
        self.db.run("UPDATE participants SET goal = -1 WHERE username='bob'")
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_tips(cursor)
            payday.update_balances(cursor)
        assert Participant.from_id(alice.id).balance == 20
        assert Participant.from_id(bob.id).balance == 0

    def test_payin_doesnt_make_null_transfers(self):
        alice = self.make_participant('alice', claimed_time='now')
        alice.set_tip_to(self.homer, 1)
        alice.set_tip_to(self.homer, 0)
        a_team = self.make_participant('a_team', claimed_time='now', number='plural')
        a_team.add_member(alice)
        Payday.start().payin()
        transfers0 = self.db.all("SELECT * FROM transfers WHERE amount = 0")
        assert not transfers0

    def test_transfer_tips(self):
        alice = self.make_participant('alice', claimed_time='now', balance=1,
                                      last_bill_result='')
        alice.set_tip_to(self.janet, D('0.51'))
        alice.set_tip_to(self.homer, D('0.50'))
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            payday.transfer_tips(cursor)
            payday.update_balances(cursor)
        alice = Participant.from_id(alice.id)
        assert Participant.from_id(alice.id).balance == D('0.49')
        assert Participant.from_id(self.janet.id).balance == D('0.51')
        assert Participant.from_id(self.homer.id).balance == 0

    def test_transfer_tips_whole_graph(self):
        alice = self.make_participant('alice', claimed_time='now', balance=0,
                                      last_bill_result='')
        alice.set_tip_to(self.homer, D('50'))
        self.homer.set_tip_to(self.janet, D('20'))
        self.janet.set_tip_to(self.david, D('5'))
        self.david.set_tip_to(self.homer, D('20'))  # Should be unfunded

        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            cursor.run("""UPDATE payday_participants
                             SET card_hold_ok = true
                           WHERE id = %s
                """, (alice.id,))
            payday.transfer_tips(cursor)
            cursor.run("""UPDATE payday_participants
                             SET new_balance = 0
                           WHERE id = %s
                """, (alice.id,))
            payday.update_balances(cursor)
        alice = Participant.from_id(alice.id)
        assert Participant.from_id(alice.id).balance == D('0')
        assert Participant.from_id(self.homer.id).balance == D('30')
        assert Participant.from_id(self.janet.id).balance == D('15')
        assert Participant.from_id(self.david.id).balance == D('5')

    def test_transfer_takes(self):
        a_team = self.make_participant('a_team', claimed_time='now', number='plural', balance=20)
        alice = self.make_participant('alice', claimed_time='now')
        a_team.add_member(alice)
        a_team.add_member(self.make_participant('bob', claimed_time='now'))
        a_team.set_take_for(alice, D('1.00'), alice)

        payday = Payday.start()

        # Test that payday ignores takes set after it started
        a_team.set_take_for(alice, D('2.00'), alice)

        # Run the transfer multiple times to make sure we ignore takes that
        # have already been processed
        for i in range(3):
            with self.db.get_cursor() as cursor:
                payday.prepare(cursor, payday.ts_start)
                payday.transfer_takes(cursor, payday.ts_start)
                payday.update_balances(cursor)

        participants = self.db.all("SELECT username, balance FROM participants")

        for p in participants:
            if p.username == 'a_team':
                assert p.balance == D('18.99')
            elif p.username == 'alice':
                assert p.balance == D('1.00')
            elif p.username == 'bob':
                assert p.balance == D('0.01')
            else:
                assert p.balance == 0

    @mock.patch.object(Payday, 'fetch_card_holds')
    def test_transfer_takes_doesnt_make_negative_transfers(self, fch):
        hold = balanced.CardHold(amount=1500, meta={'participant_id': self.janet.id},
                                 card_href=self.card_href)
        hold.capture = lambda *a, **kw: None
        hold.save = lambda *a, **kw: None
        fch.return_value = {self.janet.id: hold}
        self.janet.update_number('plural')
        self.janet.set_tip_to(self.homer, 10)
        self.janet.add_member(self.david)
        Payday.start().payin()
        assert Participant.from_id(self.david.id).balance == 0
        assert Participant.from_id(self.homer.id).balance == 10
        assert Participant.from_id(self.janet.id).balance == 0

    def test_take_over_during_payin(self):
        alice = self.make_participant('alice', claimed_time='now', balance=50)
        bob = self.make_participant('bob', claimed_time='now', elsewhere='twitter')
        alice.set_tip_to(bob, 18)
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            bruce = self.make_participant('bruce', claimed_time='now')
            bruce.take_over(('twitter', str(bob.id)), have_confirmation=True)
            payday.transfer_tips(cursor)
            bruce.delete_elsewhere('twitter', str(bob.id))
            billy = self.make_participant('billy', claimed_time='now')
            billy.take_over(('github', str(bruce.id)), have_confirmation=True)
            payday.update_balances(cursor)
        payday.take_over_balances()
        assert Participant.from_id(bob.id).balance == 0
        assert Participant.from_id(bruce.id).balance == 0
        assert Participant.from_id(billy.id).balance == 18

    @mock.patch.object(Payday, 'fetch_card_holds')
    @mock.patch('gratipay.billing.payday.capture_card_hold')
    def test_payin_dumps_transfers_for_debugging(self, cch, fch):
        self.janet.set_tip_to(self.homer, 10)
        fake_hold = mock.MagicMock()
        fake_hold.amount = 1500
        fch.return_value = {self.janet.id: fake_hold}
        cch.side_effect = Foobar
        open_ = mock.MagicMock()
        open_.side_effect = open
        with mock.patch.dict(__builtins__, {'open': open_}):
            with self.assertRaises(Foobar):
                Payday.start().payin()
        filename = open_.call_args_list[-1][0][0]
        assert filename.endswith('_transfers.csv')
        os.unlink(filename)


class TestPayout(Harness):

    def test_payout_no_balanced_href(self):
        self.make_participant('alice', claimed_time='now', is_suspicious=False,
                              balance=20)
        Payday.start().payout()

    @mock.patch('gratipay.billing.payday.log')
    def test_payout_unreviewed(self, log):
        self.make_participant('alice', claimed_time='now', is_suspicious=None,
                              balance=20, balanced_customer_href='foo',
                              last_ach_result='')
        Payday.start().payout()
        log.assert_any_call('UNREVIEWED: alice')

    @mock.patch('gratipay.billing.payday.ach_credit')
    def test_payout_ach_error(self, ach_credit):
        self.make_participant('alice', claimed_time='now', is_suspicious=False,
                              balance=20, balanced_customer_href='foo',
                              last_ach_result='')
        ach_credit.return_value = 'some error'
        Payday.start().payout()
        payday = self.fetch_payday()
        assert payday['nach_failing'] == 1


class TestNotifyParticipants(EmailHarness):

    def test_it_notifies_participants(self):
        kalel = self.make_participant('kalel', claimed_time='now', is_suspicious=False,
                                      email_address='kalel@example.net', notify_charge=3)
        lily = self.make_participant('lily', claimed_time='now', is_suspicious=False)
        kalel.set_tip_to(lily, 10)

        for status in ('failed', 'succeeded'):
            payday = Payday.start()
            self.make_exchange('balanced-cc', 10, 0, kalel, status)
            payday.end()
            payday.notify_participants()

            emails = self.db.one('SELECT * FROM email_queue')
            assert emails.spt_name == 'charge_'+status

            Participant.dequeue_emails()
            assert self.get_last_email()['to'][0]['email'] == 'kalel@example.net'
