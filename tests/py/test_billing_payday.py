from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

import balanced
import mock

from gittip.billing.payday import Payday
from gittip.models.participant import Participant
from gittip.testing import Harness
from gittip.testing.balanced import BalancedHarness


class TestPayday(BalancedHarness):

    def test_payday_moves_money(self):
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        Payday.start().run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert homer.balance == D('6.00')
        assert janet.balance == D('3.41')

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

    def test_payday_moves_money_with_balanced(self):
        self.janet.set_tip_to(self.homer, '15.00')
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

    @mock.patch('gittip.billing.payday.log')
    @mock.patch('gittip.billing.payday.Payday.payin')
    @mock.patch('gittip.billing.payday.Payday.end')
    def test_payday(self, end, payin, log):
        greeting = 'Greetings, program! It\'s PAYDAY!!!!'
        Payday.start().run()
        assert log.called_with(greeting)
        assert payin.call_count == 1
        assert end.call_count == 1


class TestPachinko(Harness):

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
