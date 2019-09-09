from datetime import datetime
from unittest import mock

from pando.utils import utc
import pytest
from types import SimpleNamespace

from liberapay.billing import transactions, watcher
from liberapay.billing.fees import (
    skim_credit,
    upcharge_bank_wire,
    upcharge_card,
)
from liberapay.billing.transactions import (
    charge,
    execute_direct_debit,
    payin_bank_wire,
    payout,
    prepare_direct_debit,
    record_exchange,
    record_exchange_result,
    refund_disputed_payin,
    sync_with_mangopay,
    transfer,
)
from liberapay.billing.payday import Payday
from liberapay.constants import EPOCH, PAYIN_CARD_MIN, PAYIN_CARD_TARGET
from liberapay.exceptions import (
    NegativeBalance, NotEnoughWithdrawableMoney, PaydayIsRunning,
    FeeExceedsAmount, AccountSuspended, Redirect,
)
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.testing import EUR, USD, Foobar
from liberapay.testing.mangopay import FakeTransfersHarness, Harness, MangopayHarness


def fail_payin(payin):
    payin.Id = -1
    payin.SecureModeRedirectURL = None
    payin.ResultCode = '1'
    payin.ResultMessage = 'oops'
    payin.Status = 'FAILED'
    return payin


class TestPayouts(MangopayHarness):

    def test_payout(self):
        e = charge(self.db, self.janet_route, EUR('46.00'), 'http://localhost/')
        assert e.status == 'succeeded', e.note
        self.janet.set_tip_to(self.homer, EUR('42.00'))
        self.janet.close('downstream')
        self.homer = self.homer.refetch()
        assert self.homer.balance == 46
        exchange = payout(self.db, self.homer_route, EUR('30.00'))
        assert exchange.note is None
        assert exchange.status == 'created'
        self.homer = self.homer.refetch()
        assert self.homer.balance == 16
        self.db.self_check()

    @mock.patch('mangopay.resources.BankAccount.get')
    def test_payout_amount_under_minimum(self, gba):
        usd_user = self.make_participant('usd_user', main_currency='USD')
        route = ExchangeRoute.insert(usd_user, 'mango-ba', 'fake ID', 'chargeable')
        self.make_exchange('mango-cc', USD(8), 0, usd_user)
        gba.return_value = self.bank_account_outside_sepa
        with self.assertRaises(FeeExceedsAmount):
            payout(self.db, route, USD('0.10'))

    @mock.patch('liberapay.billing.transactions.test_hook')
    def test_payout_failure(self, test_hook):
        test_hook.side_effect = Foobar
        self.make_exchange('mango-cc', 20, 0, self.homer)
        exchange = payout(self.db, self.homer_route, EUR('1.00'))
        assert exchange.status == 'failed'
        homer = Participant.from_id(self.homer.id)
        assert exchange.note == "Foobar()"
        assert self.homer.balance == homer.balance == 20

    def test_payout_no_route(self):
        self.make_exchange('mango-cc', 20, 0, self.david)
        with self.assertRaises(AssertionError):
            payout(self.db, None, EUR('1.00'))

    def test_payout_invalidated_bank_account(self):
        self.make_exchange('mango-cc', 20, 0, self.homer)
        self.homer_route.invalidate()
        with self.assertRaises(AssertionError):
            payout(self.db, self.homer_route, EUR('10.00'))

    @mock.patch('mangopay.resources.BankAccount.get')
    def test_payout_quarantine(self, gba):
        self.make_exchange('mango-cc', 39, 0, self.homer)
        gba.return_value = self.bank_account
        with mock.patch.multiple(transactions, QUARANTINE='1 month'):
            with self.assertRaises(NotEnoughWithdrawableMoney):
                payout(self.db, self.homer_route, EUR('32.00'))

    def test_payout_during_payday(self):
        self.make_exchange('mango-cc', 200, 0, self.homer)
        Payday.start()
        with self.assertRaises(PaydayIsRunning):
            payout(self.db, self.homer_route, EUR('97.35'))

    def test_payout_suspended_user(self):
        self.make_exchange('mango-cc', 20, 0, self.homer)
        self.db.run("""
            UPDATE participants
               SET is_suspended = true
             WHERE id = %s
        """, (self.homer.id,))
        self.homer.set_attributes(is_suspended=True)
        with self.assertRaises(AccountSuspended):
            payout(self.db, self.homer_route, EUR('10.00'))


class TestCharge(MangopayHarness):

    @mock.patch('liberapay.billing.transactions.test_hook')
    def test_charge_exception(self, test_hook):
        test_hook.side_effect = Foobar
        exchange = charge(self.db, self.janet_route, EUR('1.00'), 'http://localhost/')
        assert exchange.note == "Foobar()"
        assert exchange.amount
        assert exchange.status == 'failed'
        janet = Participant.from_id(self.janet.id)
        assert self.janet.balance == janet.balance == 0

    @mock.patch('mangopay.resources.PayIn.save', autospec=True)
    def test_charge_failure(self, save):
        save.side_effect = fail_payin
        exchange = charge(self.db, self.janet_route, EUR('1.00'), 'http://localhost/')
        error = "1: oops"
        assert exchange.note == error
        assert exchange.amount
        assert exchange.status == 'failed'
        janet = self.janet.refetch()
        assert self.janet.balance == janet.balance == 0

    def test_charge_success_and_wallet_creation(self):
        self.db.run("DELETE FROM wallets WHERE owner = %s", (self.janet.id,))
        exchange = charge(self.db, self.janet_route, EUR('20'), 'http://localhost/')
        janet = Participant.from_id(self.janet.id)
        assert exchange.note is None
        assert exchange.amount == 20
        assert exchange.status == 'succeeded'
        assert self.janet.balance == janet.balance == 20
        assert janet.get_withdrawable_amount('EUR') == 20
        with mock.patch.multiple(transactions, QUARANTINE='1 month'):
            assert janet.get_withdrawable_amount('EUR') == 0
            self.db.self_check()

    @mock.patch('mangopay.resources.PayIn.save', autospec=True)
    def test_charge_100(self, save):
        def add_redirect_url_to_payin(payin):
            payin.SecureModeRedirectURL = 'some url'
            return payin
        save.side_effect = add_redirect_url_to_payin
        with self.assertRaises(Redirect):
            charge(self.db, self.janet_route, EUR('100'), 'http://localhost/')
        janet = Participant.from_id(self.janet.id)
        assert self.janet.balance == janet.balance == 0

    def test_charge_bad_card(self):
        self.janet_route.set_attributes(address='-1')
        exchange = charge(self.db, self.janet_route, EUR('10.00'), 'http://localhost/')
        assert exchange.note.startswith('The value -1 is not valid (CardId) | Error ID: ')

    def test_charge_no_card(self):
        with self.assertRaises(AssertionError):
            charge(self.db, None, EUR('10.00'), 'http://localhost/')

    def test_charge_invalidated_card(self):
        bob = self.make_participant('bob')
        route = ExchangeRoute.insert(bob, 'mango-cc', '-1', 'canceled', currency='EUR')
        with self.assertRaises(AssertionError):
            charge(self.db, route, EUR('10.00'), 'http://localhost/')

    def test_charge_suspended_user(self):
        self.db.run("""
            UPDATE participants
               SET is_suspended = true
             WHERE id = %s
        """, (self.janet.id,))
        self.janet.set_attributes(is_suspended=True)
        with self.assertRaises(AccountSuspended):
            charge(self.db, self.janet_route, EUR('10.00'), 'http://localhost/')


class TestPayinBankWire(MangopayHarness):

    def test_payin_bank_wire_creation(self):
        path = b'/janet/wallet/payin/bankwire/'
        data = {'amount': str(upcharge_bank_wire(EUR('10.00'))[0].amount)}

        r = self.client.PxST(path, data, auth_as=self.janet)
        assert r.code == 403  # rejected because janet has no donations set up

        self.janet.set_tip_to(self.david, EUR('10.00'))
        r = self.client.PxST(path, data, auth_as=self.janet)
        assert r.code == 302, r.text
        redir = r.headers[b'Location']
        assert redir.startswith(path+b'?exchange_id=')

        r = self.client.GET(redir, auth_as=self.janet)
        assert b'IBAN' in r.body, r.text

        janet = self.janet.refetch()
        assert janet.balance == 0

    @mock.patch('liberapay.billing.transactions.test_hook')
    def test_payinbank_wire_exception_and_wallet_creation(self, test_hook):
        test_hook.side_effect = Foobar
        self.db.run("DELETE FROM wallets WHERE owner = %s", (self.janet.id,))
        exchange = payin_bank_wire(self.db, self.janet, EUR('50'))[1]
        assert exchange.note == 'Foobar()'
        assert exchange.status == 'failed'
        janet = self.janet.refetch()
        assert self.janet.balance == janet.balance == 0

    @mock.patch('mangopay.resources.PayIn.save', autospec=True)
    def test_payin_bank_wire_failure(self, save):
        save.side_effect = fail_payin
        exchange = payin_bank_wire(self.db, self.janet, EUR('1.00'))[1]
        error = "1: oops"
        assert exchange.note == error
        assert exchange.amount
        assert exchange.status == 'failed'
        janet = self.janet.refetch()
        assert self.janet.balance == janet.balance == 0


class TestDirectDebit(MangopayHarness):

    def test_direct_debit_form(self):
        path = b'/janet/wallet/payin/direct-debit'
        self.janet.set_tip_to(self.david, EUR('10.00'))
        r = self.client.GET(path, auth_as=self.janet)
        assert r.code == 200

    @mock.patch('liberapay.models.participant.Participant.url')
    def test_direct_debit_creation(self, url):
        path = b'/homer/wallet/payin/direct-debit'
        data = {'amount': '100.00'}

        url.return_value = b'https://liberapay.com' + path

        r = self.client.PxST(path, data, auth_as=self.homer)
        assert r.code == 403  # rejected because homer has no donations set up

        self.homer.set_tip_to(self.david, EUR('10.00'))
        r = self.client.GET(path, auth_as=self.homer)
        assert b'FRxxxxxxxxxxxxxxxxxxxxx2606' in r.body, r.text

        r = self.client.POST(path, data, auth_as=self.homer, raise_immediately=False)
        assert r.code == 200, r.text
        assert ';url=https://api.sandbox.mangopay.com/' in r.text

        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'pre-mandate'
        route = ExchangeRoute.from_id(self.homer, exchange.route)

        path += ('/%s?MandateId=%s' % (exchange.id, route.mandate)).encode('ascii')
        r = self.client.GET(path, auth_as=self.homer)
        assert r.code == 200

        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'failed'
        assert exchange.note == '001833: The Status of this Mandate does not allow for payments'

    @mock.patch('liberapay.billing.transactions.test_hook')
    def test_direct_debit_exception_and_wallet_creation(self, test_hook):
        test_hook.side_effect = Foobar
        self.db.run("DELETE FROM wallets WHERE owner = %s", (self.homer.id,))
        exchange = prepare_direct_debit(self.db, self.homer_route, EUR('50'))
        assert exchange.status == 'pre-mandate'
        self.homer_route.set_mandate('-1')
        exchange = execute_direct_debit(self.db, exchange, self.homer_route)
        assert exchange.note == 'Foobar()'
        assert exchange.status == 'failed'
        homer = self.homer.refetch()
        assert self.homer.balance == homer.balance == 0

    @mock.patch('mangopay.resources.PayIn.save', autospec=True)
    def test_direct_debit_failure(self, save):
        save.side_effect = fail_payin
        exchange = prepare_direct_debit(self.db, self.homer_route, EUR('1.00'))
        self.homer_route.set_mandate('-2')
        exchange = execute_direct_debit(self.db, exchange, self.homer_route)
        error = "1: oops"
        assert exchange.note == error
        assert exchange.amount
        assert exchange.status == 'failed'
        homer = self.homer.refetch()
        assert self.homer.balance == homer.balance == 0


class TestPayinRefund(MangopayHarness):

    def test_refund_disputed_payin(self):
        self.make_participant(
            'LiberapayOrg', kind='organization', balance=EUR('100.00'),
            mangopay_user_id='0', mangopay_wallet_id='0',
        )
        exchange = charge(self.db, self.janet_route, EUR('20'), 'http://localhost/')
        # Dry run
        msg, e_refund = refund_disputed_payin(self.db, exchange, dry_run=True)
        assert msg.startswith('[dry run] partial refund ')
        assert e_refund is None
        # For real
        msg, e_refund = refund_disputed_payin(self.db, exchange)
        assert msg == 'succeeded'
        assert e_refund.amount == -exchange.amount
        assert e_refund.fee == exchange.fee.zero()
        janet = self.janet.refetch()
        assert janet.balance == 0
        self.db.self_check()
        # Again
        msg, e_refund_2 = refund_disputed_payin(self.db, exchange)
        assert msg == 'already done'
        assert e_refund_2.id == e_refund.id


class TestFees(MangopayHarness):

    def test_upcharge_basically_works(self):
        actual = upcharge_card(EUR('20.00'))
        expected = (EUR('20.65'), EUR('0.65'), EUR('0.10'))
        assert actual == expected

    def test_upcharge_full_in_rounded_case(self):
        actual = upcharge_card(EUR('5.00'))
        expected = upcharge_card(PAYIN_CARD_MIN['EUR'])
        assert actual == expected

    def test_upcharge_at_min(self):
        actual = upcharge_card(PAYIN_CARD_MIN['EUR'])
        expected = (EUR('15.54'), EUR('0.54'), EUR('0.08'))
        assert actual == expected
        assert actual[1] / actual[0] < EUR('0.035')  # less than 3.5% fee

    def test_upcharge_at_target(self):
        actual = upcharge_card(PAYIN_CARD_TARGET['EUR'])
        expected = (EUR('94.19'), EUR('2.19'), EUR('0.32'))
        assert actual == expected
        assert actual[1] / actual[0] < EUR('0.024')  # less than 2.4% fee

    def test_upcharge_at_one_cent(self):
        actual = upcharge_card(EUR('0.01'))
        expected = upcharge_card(PAYIN_CARD_MIN['EUR'])
        assert actual == expected

    def test_upcharge_at_min_minus_one_cent(self):
        actual = upcharge_card(PAYIN_CARD_MIN['EUR'] - EUR('0.01'))
        expected = upcharge_card(PAYIN_CARD_MIN['EUR'])
        assert actual == expected

    def test_skim_credit(self):
        actual = skim_credit(EUR('10.00'), self.bank_account)
        assert actual == (EUR('10.00'), EUR('0.00'), EUR('0.00'))

    def test_skim_credit_outside_sepa(self):
        actual = skim_credit(EUR('10.00'), self.bank_account_outside_sepa)
        assert actual == (EUR('10.00'), EUR('0.00'), EUR('0.00'))


class TestRecordExchange(MangopayHarness):

    def test_record_exchange_doesnt_update_balance_for_positive_amounts(self):
        record_exchange(
            self.db, self.janet_route,
            amount=EUR("0.59"), fee=EUR("0.41"), vat=EUR("0.00"),
            participant=self.janet, status='pre',
        )
        janet = Participant.from_username('janet')
        assert self.janet.balance == janet.balance == EUR('0.00')

    def test_record_exchange_updates_balance_for_negative_amounts(self):
        self.make_exchange('mango-cc', 50, 0, self.homer)
        record_exchange(
            self.db,
            self.homer_route,
            amount=EUR('-35.84'),
            fee=EUR('0.75'),
            vat=EUR('0.00'),
            participant=self.homer,
            status='pre',
        )
        homer = Participant.from_username('homer')
        assert homer.balance == EUR('13.41')

    def test_record_exchange_fails_if_negative_balance(self):
        with pytest.raises(NegativeBalance):
            record_exchange(self.db, self.homer_route, EUR("-10.00"), EUR("0.41"), EUR(0), self.homer, 'pre')

    def test_record_exchange_result_restores_balance_on_error(self):
        homer, ba = self.homer, self.homer_route
        self.make_exchange('mango-cc', 30, 0, homer)
        e_id = record_exchange(self.db, ba, EUR('-27.06'), EUR('0.81'), EUR(0), homer, 'pre').id
        assert homer.balance == EUR('02.13')
        record_exchange_result(self.db, e_id, -e_id, 'failed', 'SOME ERROR', homer)
        homer = Participant.from_username('homer')
        assert homer.balance == EUR('30.00')

    def test_record_exchange_result_restores_balance_on_error_with_invalidated_route(self):
        homer, ba = self.homer, self.homer_route
        self.make_exchange('mango-cc', 37, 0, homer)
        e_id = record_exchange(self.db, ba, EUR('-32.45'), EUR('0.86'), EUR(0), homer, 'pre').id
        assert homer.balance == EUR('3.69')
        ba.update_status('canceled')
        record_exchange_result(self.db, e_id, -e_id, 'failed', 'oops', homer)
        homer = Participant.from_username('homer')
        assert homer.balance == EUR('37.00')
        assert ba.status == 'canceled'

    def test_record_exchange_result_doesnt_restore_balance_on_success(self):
        homer, ba = self.homer, self.homer_route
        self.make_exchange('mango-cc', 50, 0, homer)
        e_id = record_exchange(self.db, ba, EUR('-43.98'), EUR('1.60'), EUR(0), homer, 'pre').id
        assert homer.balance == EUR('4.42')
        record_exchange_result(self.db, e_id, -e_id, 'succeeded', None, homer)
        homer = Participant.from_username('homer')
        assert homer.balance == EUR('4.42')

    def test_record_exchange_result_updates_balance_for_positive_amounts(self):
        janet, cc = self.janet, self.janet_route
        self.make_exchange('mango-cc', 4, 0, janet)
        e_id = record_exchange(self.db, cc, EUR('31.59'), EUR('0.01'), EUR(0), janet, 'pre').id
        assert janet.balance == EUR('4.00')
        record_exchange_result(self.db, e_id, -e_id, 'succeeded', None, janet)
        janet = Participant.from_username('janet')
        assert janet.balance == EUR('35.59')


class TestCashBundles(FakeTransfersHarness, MangopayHarness):

    def test_cash_bundles_are_merged_after_transfer(self):
        bundles_count = lambda: self.db.one("SELECT count(*) FROM cash_bundles")
        assert bundles_count() == 0
        self.make_exchange('mango-cc', 45, 0, self.janet)
        assert bundles_count() == 1
        transfer(self.db, self.janet.id, self.homer.id, EUR('10.00'), 'tip')
        assert bundles_count() == 2
        transfer(self.db, self.homer.id, self.janet.id, EUR('5.00'), 'tip')
        assert bundles_count() == 2
        transfer(self.db, self.homer.id, self.janet.id, EUR('5.00'), 'tip')
        assert bundles_count() == 1
        self.db.self_check()

    def test_cash_bundles_are_merged_after_payout_failure(self):
        bundles_count = lambda: self.db.one("SELECT count(*) FROM cash_bundles")
        self.make_exchange('mango-cc', 46, 0, self.homer)
        assert bundles_count() == 1
        self.make_exchange('mango-cc', -40, 0, self.homer, status='failed')
        assert bundles_count() == 1
        self.db.self_check()


class TestSync(MangopayHarness):

    def throw_transactions_back_in_time(self):
        self.db.run("""
            UPDATE exchanges SET timestamp = timestamp - interval '1 week';
            UPDATE transfers SET timestamp = timestamp - interval '1 week';
        """)

    def test_1_sync_with_mangopay_records_exchange_success(self):
        amount = PAYIN_CARD_MIN['EUR'].amount
        with mock.patch('liberapay.billing.transactions.record_exchange_result') as rer:
            rer.side_effect = Foobar()
            with self.assertRaises(Foobar):
                charge(self.db, self.janet_route, amount, 'http://localhost/')
        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'pre'
        sync_with_mangopay(self.db)
        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'succeeded'
        assert Participant.from_username('janet').balance == amount

    def test_2_sync_with_mangopay_handles_payins_that_didnt_happen(self):
        pass  # this is for pep8
        with mock.patch('liberapay.billing.transactions.record_exchange_result') as rer, \
             mock.patch('liberapay.billing.transactions.DirectPayIn.save', autospec=True) as save:
            rer.side_effect = save.side_effect = Foobar
            with self.assertRaises(Foobar):
                charge(self.db, self.janet_route, EUR('33.67'), 'http://localhost/')
        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'pre'
        self.throw_transactions_back_in_time()
        sync_with_mangopay(self.db)
        exchange = self.db.one("SELECT * FROM exchanges")
        assert exchange.status == 'failed'
        assert exchange.note == 'interrupted'
        assert Participant.from_username('janet').balance == 0

    def test_5_sync_with_mangopay_reverts_payouts_that_didnt_happen(self):
        self.make_exchange('mango-cc', 41, 0, self.homer)
        with mock.patch('liberapay.billing.transactions.record_exchange_result') as rer, \
             mock.patch('liberapay.billing.transactions.test_hook') as test_hook:
            rer.side_effect = test_hook.side_effect = Foobar
            with self.assertRaises(Foobar):
                payout(self.db, self.homer_route, EUR('35.00'))
        exchange = self.db.one("SELECT * FROM exchanges WHERE amount < 0")
        assert exchange.status == 'pre'
        self.throw_transactions_back_in_time()
        sync_with_mangopay(self.db)
        exchange = self.db.one("SELECT * FROM exchanges WHERE amount < 0")
        assert exchange.status == 'failed'
        homer = self.homer.refetch()
        assert homer.balance == homer.get_withdrawable_amount('EUR') == 41

    def test_4_sync_with_mangopay_records_transfer_success(self):
        self.make_exchange('mango-cc', 10, 0, self.janet)
        with mock.patch('liberapay.billing.transactions.record_transfer_result') as rtr:
            rtr.side_effect = Foobar()
            with self.assertRaises(Foobar):
                transfer(self.db, self.janet.id, self.david.id, EUR('10.00'), 'tip')
        t = self.db.one("SELECT * FROM transfers")
        assert t.status == 'pre'
        sync_with_mangopay(self.db)
        t = self.db.one("SELECT * FROM transfers")
        assert t.status == 'succeeded'
        assert Participant.from_username('david').balance == 10
        assert Participant.from_username('janet').balance == 0

    def test_3_sync_with_mangopay_handles_transfers_that_didnt_happen(self):
        self.make_exchange('mango-cc', 10, 0, self.janet)
        with mock.patch('liberapay.billing.transactions._record_transfer_result') as rtr, \
             mock.patch('liberapay.billing.transactions.Transfer.save', autospec=True) as save:
            rtr.side_effect = save.side_effect = Foobar
            with self.assertRaises(Foobar):
                transfer(self.db, self.janet.id, self.david.id, EUR('10.00'), 'tip')
        t = self.db.one("SELECT * FROM transfers")
        assert t.status == 'pre'
        self.throw_transactions_back_in_time()
        sync_with_mangopay(self.db)
        t = self.db.one("SELECT * FROM transfers")
        assert t.status == 'failed'
        assert t.error == 'interrupted'
        assert Participant.from_username('david').balance == 0
        assert Participant.from_username('janet').balance == 10


class TestMangopayWatcher(Harness):

    def on_response(self, *consumed):
        assert len(consumed) <= 4
        c1, c2, c3, c4 = (consumed * 4)[:4]
        remaining = (2300 - c1, 4500 - c2, 8800 - c3, 105600 - c4)
        now = datetime.utcnow().replace(tzinfo=utc)
        ts_now = int((now - EPOCH).total_seconds())
        reset = (ts_now + 15*60, ts_now + 30*60, ts_now + 60*60, ts_now + 24*60*60)
        watcher.on_response(None, result=SimpleNamespace(headers={
            'X-RateLimit': ', '.join(map(str, consumed)),
            'X-RateLimit-Remaining': ', '.join(map(str, remaining)),
            'X-RateLimit-Reset': ', '.join(map(str, reset)),
        }))

    def test_mangopay_watcher_tells_payday_to_slow_down(self):
        self.on_response(1)
        assert Payday.transfer_delay == 0
        self.on_response(int(0.61 * 2300))
        assert Payday.transfer_delay > 1
        self.on_response(int(0.85 * 2300))
        assert Payday.transfer_delay > 2

    def test_mangopay_watcher_handles_errors_gracefully(self):
        with mock.patch.object(self.website, 'tell_sentry') as tell_sentry:
            watcher.on_response(None, result=None)
            assert tell_sentry.called
