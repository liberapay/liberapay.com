from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

import balanced
import mock
from psycopg2 import IntegrityError

from aspen.utils import utcnow
from gittip.billing.payday import Payday
from gittip.exceptions import NegativeBalance
from gittip.models.participant import Participant
from gittip.testing import Harness
from gittip.testing.balanced import BalancedHarness


class PaydayHarness(BalancedHarness):

    def setUp(self):
        BalancedHarness.setUp(self)
        self.payday = Payday(self.db)
        self.alice = self.make_participant('alice', claimed_time='now')

    def fetch_payday(self):
        return self.db.one("SELECT * FROM paydays", back_as=dict)


class TestPayday(PaydayHarness):

    @mock.patch('gittip.billing.exchanges.charge_on_balanced')
    def test_payday_moves_money(self, charge_on_balanced):
        charge_on_balanced.return_value = (D('10.00'), D('0.68'), "")
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        self.payday.run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert homer.balance == D('6.00')
        assert janet.balance == D('3.32')

    @mock.patch('gittip.billing.exchanges.charge_on_balanced')
    def test_payday_doesnt_move_money_from_a_suspicious_account(self, charge_on_balanced):
        charge_on_balanced.return_value = (D('10.00'), D('0.68'), "")
        self.db.run("""
            UPDATE participants
               SET is_suspicious = true
             WHERE username = 'janet'
        """)
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        self.payday.run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert janet.balance == D('0.00')
        assert homer.balance == D('0.00')

    @mock.patch('gittip.billing.exchanges.charge_on_balanced')
    def test_payday_doesnt_move_money_to_a_suspicious_account(self, charge_on_balanced):
        charge_on_balanced.return_value = (D('10.00'), D('0.68'), "")
        self.db.run("""
            UPDATE participants
               SET is_suspicious = true
             WHERE username = 'homer'
        """)
        self.janet.set_tip_to(self.homer, '6.00')  # under $10!
        self.payday.run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert janet.balance == D('0.00')
        assert homer.balance == D('0.00')

    def test_payday_moves_money_with_balanced(self):
        self.janet.set_tip_to(self.homer, '15.00')
        self.payday.run()

        janet = Participant.from_username('janet')
        homer = Participant.from_username('homer')

        assert janet.balance == D('0.00')
        assert homer.balance == D('0.00')

        janet_customer = balanced.Customer.fetch(janet.balanced_customer_href)
        homer_customer = balanced.Customer.fetch(homer.balanced_customer_href)

        homer_credits = homer_customer.credits.all()
        assert len(homer_credits) >= 1
        assert homer_credits[0].amount == 1500
        assert homer_credits[0].description == 'homer'

        janet_debits = janet_customer.debits.all()
        assert len(janet_debits) >= 1
        assert janet_debits[0].amount == 1576  # base amount + fee
        assert janet_debits[0].description == 'janet'


class TestBillingCharges(PaydayHarness):

    def test_mark_missing_funding(self):
        self.payday.start()
        before = self.fetch_payday()
        missing_count = before['ncc_missing']

        self.payday.mark_missing_funding()

        after = self.fetch_payday()
        assert after['ncc_missing'] == missing_count + 1

    def test_mark_charge_failed(self):
        self.payday.start()
        before = self.fetch_payday()
        fail_count = before['ncc_failing']

        self.payday.mark_charge_failed()

        after = self.fetch_payday()
        assert after['ncc_failing'] == fail_count + 1


class TestBillingPayday(PaydayHarness):

    def test_move_pending_to_balance_for_teams_does_so(self):
        self.make_participant('A', number='plural', balance=2, pending=3)
        self.payday.move_pending_to_balance_for_teams()
        actual = self.db.one("SELECT balance FROM participants WHERE username='A'")
        assert actual == 5

    def test_move_pending_to_balance_for_teams_ignores_new_teams(self):
        # See https://github.com/gittip/www.gittip.com/issues/1684
        self.make_participant('A', number='plural', balance=0, pending=None)
        self.payday.move_pending_to_balance_for_teams()
        actual = self.db.one("SELECT balance FROM participants WHERE username='A'")
        assert actual == 0

    def test_update_receiving_amounts_updates_receiving_amounts(self):
        A = self.make_participant('A')
        B = self.make_participant('B', claimed_time='now', last_bill_result='')
        B.set_tip_to(A, D('10.00'), update_tippee=False)
        assert Participant.from_username('A').receiving == 0

        self.payday.update_receiving_amounts()
        assert Participant.from_username('A').receiving == 10

    def test_update_receiving_amounts_includes_taking(self):
        A = self.make_participant('A', claimed_time='now', taking=3)
        B = self.make_participant('B', claimed_time='now', last_bill_result='')
        B.set_tip_to(A, D('10.00'), update_tippee=False)

        assert Participant.from_username('A').receiving == 0
        assert Participant.from_username('A').taking == 3

        self.payday.update_receiving_amounts()
        assert Participant.from_username('A').receiving == 13
        assert Participant.from_username('A').taking == 3

    @mock.patch('gittip.billing.payday.Payday.transfer')
    @mock.patch('gittip.billing.payday.log')
    def test_tip(self, log, transfer):
        self.db.run("""
            UPDATE participants
               SET balance=1
             WHERE username='janet'
        """)
        amount = D('1.00')
        invalid_amount = D('0.00')
        tip = { 'amount': amount
              , 'tippee': 'janet'
              , 'claimed_time': utcnow()
               }

        result = self.payday.tip(self.janet, tip)
        assert result == 1
        result = transfer.called_with('janet', tip['tippee'], tip['amount'])
        assert result

        assert log.called_with('SUCCESS: $1 from mjallday to alice.')

        # XXX: Should these tests be broken down to a separate class with the
        # common setup factored in to a setUp method.

        # XXX: We should have constants to compare the values to
        # invalid amount
        tip['amount'] = invalid_amount
        result = self.payday.tip(self.janet, tip)
        assert result == 0

        tip['amount'] = amount

        # XXX: We should have constants to compare the values to
        # transfer failed
        transfer.return_value = False
        result = self.payday.tip(self.janet, tip)
        assert result == -1

    @mock.patch('gittip.billing.payday.log')
    def test_start_prepare_and_zero_out(self, log):
        self.clear_tables()
        self.make_participant('bob', balance=10, claimed_time=None, pending=1)
        self.make_participant('carl', balance=10, claimed_time='now', pending=1)

        ts_start = self.payday.start()

        get_participants = lambda: self.db.all("SELECT * FROM pay_participants")

        self.payday.prepare(ts_start)
        self.payday.zero_out_pending(ts_start)

        participants = get_participants()

        expected_logging_call_args = [
            ('Starting a new payday.'),
            ('Payday started at {}.'.format(ts_start)),
            ('Prepared the DB.'),
            ('Zeroed out the pending column.'),
        ]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            assert args[0] == expected_logging_call_args.pop()

        log.reset_mock()

        # run a second time, we should see it pick up the existing payday
        second_ts_start = self.payday.start()
        self.payday.prepare(second_ts_start)
        self.payday.zero_out_pending(second_ts_start)
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
            ('Zeroed out the pending column.')]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            assert args[0] == expected_logging_call_args.pop()

    @mock.patch('gittip.billing.payday.log')
    def test_end(self, log):
        self.payday.start()
        self.payday.end()
        assert log.called_with('Finished payday.')

        # finishing the payday will set the ts_end date on this payday record
        # to now, so this will not return any result
        result = self.db.one("SELECT count(*) FROM paydays "
                             "WHERE ts_end > '1970-01-01'")
        assert result == 1

    @mock.patch('gittip.billing.payday.log')
    @mock.patch('gittip.billing.payday.Payday.start')
    @mock.patch('gittip.billing.payday.Payday.payin')
    @mock.patch('gittip.billing.payday.Payday.end')
    def test_payday(self, end, payin, init, log):
        ts_start = utcnow()
        init.return_value = (ts_start,)
        greeting = 'Greetings, program! It\'s PAYDAY!!!!'

        self.payday.run()

        assert log.called_with(greeting)
        assert init.call_count
        assert payin.called_with(init.return_value)
        assert end.call_count


class TestBillingTransfer(PaydayHarness):
    def setUp(self):
        PaydayHarness.setUp(self)
        self.payday.start()
        self.tipper = self.make_participant('lgtest')

    def test_transfer(self):
        amount = D('1.00')
        sender = self.make_participant('test_transfer_sender', pending=0,
                                       balance=1)
        recipient = self.make_participant('test_transfer_recipient', pending=0,
                                          balance=1)

        result = self.payday.transfer( sender.username
                                     , recipient.username
                                     , amount
                                      )
        assert result == True

        # no balance remaining for a second transfer
        result = self.payday.transfer( sender.username
                                     , recipient.username
                                     , amount
                                      )
        assert result == False

    def test_debit_participant(self):
        amount = D('1.00')
        subject = self.make_participant('test_debit_participant', pending=0,
                                        balance=1)

        initial_amount = subject.balance

        with self.db.get_cursor() as cursor:
            self.payday.debit_participant(cursor, subject.username, amount)

        subject = Participant.from_username('test_debit_participant')

        expected = initial_amount - amount
        actual = subject.balance
        assert actual == expected

        # this will fail because not enough balance
        with self.db.get_cursor() as cursor:
            with self.assertRaises(NegativeBalance):
                self.payday.debit_participant(cursor, subject.username, amount)

    def test_credit_participant(self):
        amount = D('1.00')
        subject = self.make_participant('test_credit_participant', pending=0,
                                        balance=1)

        initial_amount = subject.pending

        with self.db.get_cursor() as cursor:
            self.payday.credit_participant(cursor, subject.username, amount)

        subject = Participant.from_username('test_credit_participant') # reload

        expected = initial_amount + amount
        actual = subject.pending
        assert actual == expected

    def test_record_transfer(self):
        amount = D('1.00')
        subjects = ['jim', 'kate', 'bob']

        for subject in subjects:
            self.make_participant(subject, balance=1, pending=0)

        with self.db.get_cursor() as cursor:
            # Tip 'jim' twice
            for recipient in ['jim'] + subjects:
                self.payday.record_transfer( cursor
                                           , self.tipper.username
                                           , recipient
                                           , amount
                                           , 'tip'
                                            )

        for subject in subjects:
            # 'jim' is tipped twice
            expected = amount * 2 if subject == 'jim' else amount
            actual = self.db.one( "SELECT sum(amount) FROM transfers "
                                  "WHERE tippee=%s"
                                , (subject,)
                                 )
            assert actual == expected

    def test_record_transfer_invalid_participant(self):
        amount = D('1.00')

        with self.db.get_cursor() as cursor:
            with self.assertRaises(IntegrityError):
                self.payday.record_transfer( cursor
                                           , 'idontexist'
                                           , 'nori'
                                           , amount
                                           , 'tip'
                                            )


class TestPachinko(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.payday = Payday(self.db)

    def test_pachinko_pachinkos(self):
        a_team = self.make_participant('a_team', claimed_time='now', number='plural', balance=20, \
                                                                                         pending=0)
        a_team.add_member(self.make_participant('alice', claimed_time='now', balance=0, pending=0))
        a_team.add_member(self.make_participant('bob', claimed_time='now', balance=0, pending=0))

        ts_start = self.payday.start()

        self.payday.prepare(ts_start)
        self.payday.pachinko()

        assert Participant.from_username('alice').pending == D('0.01')
        assert Participant.from_username('bob').pending == D('0.01')

    def test_pachinko_sees_current_take(self):
        a_team = self.make_participant('a_team', claimed_time='now', number='plural', balance=20, \
                                                                                         pending=0)
        alice = self.make_participant('alice', claimed_time='now', balance=0, pending=0)
        a_team.add_member(alice)
        a_team.set_take_for(alice, D('1.00'), alice)

        ts_start = self.payday.start()

        self.payday.prepare(ts_start)
        self.payday.pachinko()

        assert Participant.from_username('alice').pending == D('1.00')

    def test_pachinko_ignores_take_set_after_payday_starts(self):
        a_team = self.make_participant('a_team', claimed_time='now', number='plural', balance=20, \
                                                                                         pending=0)
        alice = self.make_participant('alice', claimed_time='now', balance=0, pending=0)
        a_team.add_member(alice)
        a_team.set_take_for(alice, D('0.33'), alice)

        ts_start = self.payday.start()
        a_team.set_take_for(alice, D('1.00'), alice)

        self.payday.prepare(ts_start)
        self.payday.pachinko()

        assert Participant.from_username('alice').pending == D('0.33')

    def test_pachinko_ignores_take_thats_already_been_processed(self):
        a_team = self.make_participant('a_team', claimed_time='now', number='plural', balance=20, \
                                                                                         pending=0)
        alice = self.make_participant('alice', claimed_time='now', balance=0, pending=0)
        a_team.add_member(alice)
        a_team.set_take_for(alice, D('0.33'), alice)

        ts_start = self.payday.start()
        a_team.set_take_for(alice, D('1.00'), alice)

        for i in range(4):
            self.payday.prepare(ts_start)
            self.payday.pachinko()

        assert Participant.from_username('alice').pending == D('0.33')
