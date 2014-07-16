from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

import balanced
import mock

from gittip.billing.exchanges import create_card_hold
from gittip.billing.payday import NoPayday, Payday
from gittip.exceptions import NegativeBalance
from gittip.models.participant import Participant
from gittip.testing import Harness, raise_foobar
from gittip.testing.balanced import BalancedHarness


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

        credit = homer_customer.credits.first()
        assert credit.amount == 1500
        assert credit.description == 'homer'

        debit = janet_customer.debits.first()
        assert debit.amount == 1576  # base amount + fee
        assert debit.description == 'janet'

    def test_mark_charge_failed(self):
        payday = Payday.start()
        before = self.fetch_payday()
        with self.db.get_cursor() as cursor:
            payday.mark_charge_failed(cursor)
        after = self.fetch_payday()
        assert after['ncc_failing'] == before['ncc_failing'] + 1

    def test_update_receiving_amounts_updates_receiving_amounts(self):
        A = self.make_participant('A')
        B = self.make_participant('B', claimed_time='now', last_bill_result='')
        B.set_tip_to(A, D('10.00'), update_tippee=False)
        assert Participant.from_username('A').receiving == 0

        Payday.start().update_receiving_amounts()
        assert Participant.from_username('A').receiving == 10

    def test_update_receiving_amounts_includes_taking(self):
        A = self.make_participant('A', claimed_time='now', taking=3)
        B = self.make_participant('B', claimed_time='now', last_bill_result='')
        B.set_tip_to(A, D('10.00'), update_tippee=False)

        assert Participant.from_username('A').receiving == 0
        assert Participant.from_username('A').taking == 3

        Payday.start().update_receiving_amounts()
        assert Participant.from_username('A').receiving == 13
        assert Participant.from_username('A').taking == 3

    @mock.patch('gittip.billing.payday.log')
    def test_start_prepare(self, log):
        self.clear_tables()
        self.make_participant('bob', balance=10, claimed_time=None)
        self.make_participant('carl', balance=10, claimed_time='now')

        payday = Payday.start()
        ts_start = payday.ts_start

        get_participants = lambda: self.db.all("SELECT * FROM pay_participants")

        payday.prepare(self.db, ts_start)

        participants = get_participants()

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
        payday.prepare(self.db, second_ts_start)
        second_participants = get_participants()

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

    @mock.patch('gittip.billing.payday.log')
    @mock.patch('gittip.billing.payday.Payday.payin')
    @mock.patch('gittip.billing.payday.Payday.end')
    def test_payday(self, end, payin, log):
        greeting = 'Greetings, program! It\'s PAYDAY!!!!'
        Payday.start().run()
        log.assert_any_call(greeting)
        assert payin.call_count == 1
        assert end.call_count == 1


class TestPayin(BalancedHarness):

    def create_card_holds(self):
        payday = Payday.start()
        with self.db.get_cursor() as cursor:
            payday.prepare(cursor, payday.ts_start)
            return payday.create_card_holds(cursor)

    @mock.patch.object(Payday, 'fetch_card_holds')
    @mock.patch('gittip.billing.payday.create_card_hold')
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
        with mock.patch('gittip.billing.payday.create_card_hold') as cch:
            cch.return_value = (None, None)
            self.create_card_holds()
            assert not cch.called, cch.call_args_list

    @mock.patch.object(Payday, 'fetch_card_holds')
    def test_payin_cancels_existing_holds_of_insufficient_amounts(self, fch):
        self.janet.set_tip_to(self.homer, 30)
        hold, error = create_card_hold(self.db, self.janet, D(10))
        assert not error
        fch.return_value = {self.janet.id: hold}
        with mock.patch('gittip.billing.payday.create_card_hold') as cch:
            fake_hold = object()
            cch.return_value = (fake_hold, None)
            holds = self.create_card_holds()
            assert len(holds) == 1
            assert holds[self.janet.id] is fake_hold
            assert hold.voided_at is not None

    @mock.patch('gittip.billing.payday.CardHold')
    @mock.patch('gittip.billing.payday.cancel_card_hold')
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

    @mock.patch('gittip.billing.payday.log')
    def test_payin_cancels_uncaptured_holds(self, log):
        self.janet.set_tip_to(self.homer, 42)
        alice = self.make_participant('alice', claimed_time='now',
                                      is_suspicious=False, balance=50)
        self.db.run("""
            INSERT INTO exchanges
                        (amount, fee, participant)
                 VALUES (50, 0, 'alice');
        """)
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
                UPDATE pay_participants
                   SET new_balance = -50
                 WHERE username IN ('janet', 'homer')
            """)
            with self.assertRaises(NegativeBalance):
                payday.update_balances(cursor)

    @mock.patch.object(Payday, 'fetch_card_holds')
    @mock.patch('balanced.Customer')
    def test_card_hold_error(self, Customer, fch):
        self.janet.set_tip_to(self.homer, 17)
        Customer.fetch = raise_foobar
        fch.return_value = {}
        Payday.start().payin()
        payday = self.fetch_payday()
        assert payday['ncc_failing'] == 1

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
            payday.prepare(self.db, payday.ts_start)
            payday.transfer_takes(self.db, payday.ts_start)
            payday.update_balances(self.db)

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


class TestPayout(Harness):

    def test_payout_no_balanced_href(self):
        self.make_participant('alice', claimed_time='now', is_suspicious=False,
                              balance=20)
        Payday.start().payout()

    @mock.patch('gittip.billing.payday.ach_credit')
    def test_payout_ach_error(self, ach_credit):
        self.make_participant('alice', claimed_time='now', is_suspicious=False,
                              balance=20)
        ach_credit.return_value = 'some error'
        Payday.start().payout()
        payday = self.fetch_payday()
        assert payday['nach_failing'] == 1
