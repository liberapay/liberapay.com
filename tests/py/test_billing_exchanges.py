from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

from aspen import Response
import mock
import pytest

from liberapay.billing import exchanges
from liberapay.billing.exchanges import (
    upcharge,
    payout,
    charge,
    record_exchange,
    record_exchange_result,
    skim_credit,
    sync_with_mangopay,
    transfer,
)
from liberapay.billing.payday import Payday
from liberapay.constants import CHARGE_MIN, CHARGE_TARGET
from liberapay.exceptions import (
    NegativeBalance, NotEnoughWithdrawableMoney, PaydayIsRunning,
    FeeExceedsAmount,
)
from liberapay.models.participant import Participant
from liberapay.testing import Foobar
from liberapay.testing.mangopay import MangopayHarness


class TestPayouts(MangopayHarness):

    def test_payout(self):
        e = charge(self.db, self.janet, D('46.00'), 'http://localhost/')
        assert e.status == 'succeeded', e.note
        self.janet.set_tip_to(self.homer, '42.00')
        self.janet.close('downstream')
        self.homer = self.homer.refetch()
        assert self.homer.balance == 46
        exchange = payout(self.db, self.homer, D('30.00'))
        assert exchange.note is None
        assert exchange.status == 'created'
        homer = Participant.from_id(self.homer.id)
        assert self.homer.balance == homer.balance == 16
        self.db.self_check()

    @mock.patch('mangopaysdk.tools.apiusers.ApiUsers.GetBankAccount')
    def test_payout_amount_under_minimum(self, gba):
        self.make_exchange('mango-cc', 8, 0, self.homer)
        gba.return_value = self.bank_account_outside_sepa
        with self.assertRaises(FeeExceedsAmount):
            payout(self.db, self.homer, D('0.10'))

    @mock.patch('liberapay.billing.exchanges.test_hook')
    def test_payout_failure(self, test_hook):
        test_hook.side_effect = Foobar
        self.make_exchange('mango-cc', 20, 0, self.homer)
        exchange = payout(self.db, self.homer, D('1.00'))
        assert exchange.status == 'failed'
        homer = Participant.from_id(self.homer.id)
        assert homer.get_bank_account_error() == exchange.note == "Foobar()"
        assert self.homer.balance == homer.balance == 20

    def test_payout_no_bank_account(self):
        self.make_exchange('mango-cc', 20, 0, self.david)
        with self.assertRaises(AssertionError):
            payout(self.db, self.david, D('1.00'))

    def test_payout_invalidated_bank_account(self):
        self.make_exchange('mango-cc', 20, 0, self.homer)
        self.homer_route.invalidate()
        with self.assertRaises(AssertionError):
            payout(self.db, self.homer, D('10.00'))

    @mock.patch('mangopaysdk.tools.apiusers.ApiUsers.GetBankAccount')
    def test_payout_quarantine(self, gba):
        self.make_exchange('mango-cc', 39, 0, self.homer)
        gba.return_value = self.bank_account
        with mock.patch.multiple(exchanges, QUARANTINE='1 month'):
            with self.assertRaises(NotEnoughWithdrawableMoney):
                payout(self.db, self.homer, D('32.00'))

    def test_payout_during_payday(self):
        self.make_exchange('mango-cc', 200, 0, self.homer)
        Payday.start()
        with self.assertRaises(PaydayIsRunning):
            payout(self.db, self.homer, D('97.35'))


class TestCharge(MangopayHarness):

    @mock.patch('liberapay.billing.exchanges.test_hook')
    def test_charge_exception(self, test_hook):
        test_hook.side_effect = Foobar
        exchange = charge(self.db, self.janet, D('1.00'), 'http://localhost/')
        assert exchange.note == "Foobar()"
        assert exchange.amount
        assert exchange.status == 'failed'
        janet = Participant.from_id(self.janet.id)
        assert self.janet.get_credit_card_error() == 'Foobar()'
        assert self.janet.balance == janet.balance == 0

    @mock.patch('mangopaysdk.tools.apipayins.ApiPayIns.Create')
    def test_charge_failure(self, Create):
        def fail_payin(payin):
            payin.ExecutionDetails.SecureModeRedirectURL = None
            payin.ResultCode = '1'
            payin.ResultMessage = 'oops'
            payin.Status = 'FAILED'
            return payin
        Create.side_effect = fail_payin
        exchange = charge(self.db, self.janet, D('1.00'), 'http://localhost/')
        error = "1: oops"
        assert exchange.note == error
        assert exchange.amount
        assert exchange.status == 'failed'
        janet = self.janet.refetch()
        assert self.janet.get_credit_card_error() == error
        assert self.janet.balance == janet.balance == 0

    def test_charge_success_and_wallet_creation(self):
        self.db.run("UPDATE participants SET mangopay_wallet_id = NULL")
        self.janet.set_attributes(mangopay_wallet_id=None)
        exchange = charge(self.db, self.janet, D('50'), 'http://localhost/')
        janet = Participant.from_id(self.janet.id)
        assert exchange.note is None
        assert exchange.amount == 50
        assert exchange.status == 'succeeded'
        assert self.janet.balance == janet.balance == 50
        assert janet.withdrawable_balance == 50
        with mock.patch.multiple(exchanges, QUARANTINE='1 month'):
            assert janet.withdrawable_balance == 0
            self.db.self_check()

    @mock.patch('mangopaysdk.tools.apipayins.ApiPayIns.Create')
    def test_charge_100(self, Create):
        def add_redirect_url_to_payin(payin):
            payin.ExecutionDetails.SecureModeRedirectURL = 'some url'
            return payin
        Create.side_effect = add_redirect_url_to_payin
        with self.assertRaises(Response) as cm:
            charge(self.db, self.janet, D('100'), 'http://localhost/')
        r = cm.exception
        assert r.code == 302
        janet = Participant.from_id(self.janet.id)
        assert self.janet.balance == janet.balance == 0

    def test_charge_bad_card(self):
        self.db.run("UPDATE exchange_routes SET address = '-1'")
        exchange = charge(self.db, self.janet, D('10.00'), 'http://localhost/')
        assert 'CardId: The value -1 is not valid' in exchange.note

    def test_charge_no_card(self):
        bob = self.make_participant('bob')
        with self.assertRaises(AssertionError):
            charge(self.db, bob, D('10.00'), 'http://localhost/')

    def test_charge_invalidated_card(self):
        bob = self.make_participant('bob', last_bill_result='invalidated')
        with self.assertRaises(AssertionError):
            charge(self.db, bob, D('10.00'), 'http://localhost/')


class TestFees(MangopayHarness):

    def test_upcharge_basically_works(self):
        actual = upcharge(D('20.00'))
        expected = (D('20.65'), D('0.65'), D('0.10'))
        assert actual == expected

    def test_upcharge_full_in_rounded_case(self):
        actual = upcharge(D('5.00'))
        expected = upcharge(CHARGE_MIN)
        assert actual == expected

    def test_upcharge_at_min(self):
        actual = upcharge(CHARGE_MIN)
        expected = (D('15.54'), D('0.54'), D('0.08'))
        assert actual == expected
        assert actual[1] / actual[0] < D('0.035')  # less than 3.5% fee

    def test_upcharge_at_target(self):
        actual = upcharge(CHARGE_TARGET)
        expected = (D('94.19'), D('2.19'), D('0.32'))
        assert actual == expected
        assert actual[1] / actual[0] < D('0.024')  # less than 2.4% fee

    def test_upcharge_at_one_cent(self):
        actual = upcharge(D('0.01'))
        expected = upcharge(CHARGE_MIN)
        assert actual == expected

    def test_upcharge_at_min_minus_one_cent(self):
        actual = upcharge(CHARGE_MIN - D('0.01'))
        expected = upcharge(CHARGE_MIN)
        assert actual == expected

    def test_skim_credit(self):
        actual = skim_credit(D('10.00'), self.bank_account)
        assert actual == (D('10.00'), D('0.00'), D('0.00'))

    def test_skim_credit_outside_sepa(self):
        actual = skim_credit(D('10.00'), self.bank_account_outside_sepa)
        assert actual == (D('7.07'), D('2.93'), D('0.43'))


class TestRecordExchange(MangopayHarness):

    def test_record_exchange_doesnt_update_balance_for_positive_amounts(self):
        record_exchange(self.db, self.janet_route, amount=D("0.59"), fee=D("0.41"), vat=D("0.00"), participant=self.janet, status='pre'
                        )
        janet = Participant.from_username('janet')
        assert self.janet.balance == janet.balance == D('0.00')

    def test_record_exchange_updates_balance_for_negative_amounts(self):
        self.make_exchange('mango-cc', 50, 0, self.homer)
        record_exchange(
            self.db,
            self.homer_route,
            amount=D('-35.84'),
            fee=D('0.75'),
            vat=D('0.00'),
            participant=self.homer,
            status='pre',
        )
        homer = Participant.from_username('homer')
        assert homer.balance == D('13.41')

    def test_record_exchange_fails_if_negative_balance(self):
        with pytest.raises(NegativeBalance):
            record_exchange(self.db, self.homer_route, D("-10.00"), D("0.41"), 0, self.homer, 'pre')

    def test_record_exchange_failure(self):
        record_exchange(self.db, self.janet_route, D("10.00"), D("0.01"), 0, self.janet, 'failed', 'OOPS')
        janet = Participant.from_id(self.janet.id)
        assert self.janet.balance == janet.balance == 0
        assert self.janet_route.error == 'OOPS'

    def test_record_exchange_result_restores_balance_on_error(self):
        homer, ba = self.homer, self.homer_route
        self.make_exchange('mango-cc', 30, 0, homer)
        e_id = record_exchange(self.db, ba, D('-27.06'), D('0.81'), 0, homer, 'pre')
        assert homer.balance == D('02.13')
        record_exchange_result(self.db, e_id, 'failed', 'SOME ERROR', homer)
        homer = Participant.from_username('homer')
        assert homer.balance == D('30.00')

    def test_record_exchange_result_restores_balance_on_error_with_invalidated_route(self):
        homer, ba = self.homer, self.homer_route
        self.make_exchange('mango-cc', 37, 0, homer)
        e_id = record_exchange(self.db, ba, D('-32.45'), D('0.86'), 0, homer, 'pre')
        assert homer.balance == D('3.69')
        ba.update_error('invalidated')
        record_exchange_result(self.db, e_id, 'failed', 'oops', homer)
        homer = Participant.from_username('homer')
        assert homer.balance == D('37.00')
        assert ba.error == homer.get_bank_account_error() == 'invalidated'

    def test_record_exchange_result_doesnt_restore_balance_on_success(self):
        homer, ba = self.homer, self.homer_route
        self.make_exchange('mango-cc', 50, 0, homer)
        e_id = record_exchange(self.db, ba, D('-43.98'), D('1.60'), 0, homer, 'pre')
        assert homer.balance == D('4.42')
        record_exchange_result(self.db, e_id, 'succeeded', None, homer)
        homer = Participant.from_username('homer')
        assert homer.balance == D('4.42')

    def test_record_exchange_result_updates_balance_for_positive_amounts(self):
        janet, cc = self.janet, self.janet_route
        self.make_exchange('mango-cc', 4, 0, janet)
        e_id = record_exchange(self.db, cc, D('31.59'), D('0.01'), 0, janet, 'pre')
        assert janet.balance == D('4.00')
        record_exchange_result(self.db, e_id, 'succeeded', None, janet)
        janet = Participant.from_username('janet')
        assert janet.balance == D('35.59')


class TestSync(MangopayHarness):

    def test_sync_with_mangopay(self):
        with mock.patch('liberapay.billing.exchanges.record_exchange_result') as rer:
            rer.side_effect = Foobar()
            with self.assertRaises(Foobar):
                charge(self.db, self.janet, CHARGE_MIN, 'http://localhost/')
        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'pre'
        sync_with_mangopay(self.db)
        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'succeeded'
        assert Participant.from_username('janet').balance == CHARGE_MIN

    def test_sync_with_mangopay_deletes_charges_that_didnt_happen(self):
        with mock.patch('liberapay.billing.exchanges.record_exchange_result') as rer \
           , mock.patch('liberapay.billing.mangoapi.payIns.Create') as Create:
            rer.side_effect = Create.side_effect = Foobar
            with self.assertRaises(Foobar):
                charge(self.db, self.janet, D('33.67'), 'http://localhost/')
        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'pre'
        sync_with_mangopay(self.db)
        exchanges = self.db.all("SELECT * FROM exchanges")
        assert not exchanges
        assert Participant.from_username('janet').balance == 0

    def test_sync_with_mangopay_reverts_credits_that_didnt_happen(self):
        self.make_exchange('mango-cc', 41, 0, self.homer)
        with mock.patch('liberapay.billing.exchanges.record_exchange_result') as rer \
                , mock.patch('liberapay.billing.exchanges.test_hook') as test_hook:
            rer.side_effect = test_hook.side_effect = Foobar
            with self.assertRaises(Foobar):
                payout(self.db, self.homer, D('35.00'))
        exchange = self.db.one("SELECT * FROM exchanges WHERE amount < 0")
        assert exchange.status == 'pre'
        sync_with_mangopay(self.db)
        exchange = self.db.one("SELECT * FROM exchanges WHERE amount < 0")
        assert exchange.status == 'failed'
        homer = self.homer.refetch()
        assert homer.balance == homer.withdrawable_balance == 41

    def test_sync_with_mangopay_transfers(self):
        self.make_exchange('mango-cc', 10, 0, self.janet)
        with mock.patch('liberapay.billing.exchanges.record_transfer_result') as rtr:
            rtr.side_effect = Foobar()
            with self.assertRaises(Foobar):
                transfer(self.db, self.janet.id, self.david.id, D('10.00'), 'tip')
        t = self.db.one("SELECT * FROM transfers")
        assert t.status == 'pre'
        sync_with_mangopay(self.db)
        t = self.db.one("SELECT * FROM transfers")
        assert t.status == 'succeeded'
        assert Participant.from_username('david').balance == 10
        assert Participant.from_username('janet').balance == 0

    def test_sync_with_mangopay_deletes_transfers_that_didnt_happen(self):
        self.make_exchange('mango-cc', 10, 0, self.janet)
        with mock.patch('liberapay.billing.exchanges.record_transfer_result') as rtr \
                , mock.patch('liberapay.billing.mangoapi.transfers.Create') as Create:
            rtr.side_effect = Create.side_effect = Foobar
            with self.assertRaises(Foobar):
                transfer(self.db, self.janet.id, self.david.id, D('10.00'), 'tip')
        t = self.db.one("SELECT * FROM transfers")
        assert t.status == 'pre'
        sync_with_mangopay(self.db)
        transfers = self.db.all("SELECT * FROM transfers")
        assert not transfers
        assert Participant.from_username('david').balance == 0
        assert Participant.from_username('janet').balance == 10
