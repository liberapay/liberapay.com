from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

from mock import patch

from mangopay.resources import BankWirePayOut, BankWirePayIn, Refund
from mangopay.utils import Reason

from liberapay.billing.exchanges import Money, record_exchange
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.security.csrf import CSRF_TOKEN
from liberapay.testing.emails import EmailHarness
from liberapay.testing.mangopay import MangopayHarness


class TestMangopayCallbacks(EmailHarness, MangopayHarness):

    def callback(self, qs, **kw):
        kw.setdefault('HTTP_ACCEPT', b'application/json')
        kw.setdefault('raise_immediately', False)
        return self.client.GET('/callbacks/mangopay?'+qs, **kw)

    @patch('mangopay.resources.BankWirePayOut.get')
    def test_payout_callback(self, Get):
        homer, ba = self.homer, self.homer_route
        for status in ('succeeded', 'failed'):
            status_up = status.upper()
            error = 'FOO' if status == 'failed' else None
            self.make_exchange('mango-cc', 10, 0, homer)
            e_id = record_exchange(self.db, ba, -10, 0, 0, homer, 'pre')
            assert homer.balance == 0
            homer.close(None)
            assert homer.status == 'closed'
            qs = "EventType=PAYOUT_NORMAL_"+status_up+"&RessourceId=123456790"
            payout = BankWirePayOut()
            payout.Status = status_up
            payout.ResultCode = '000001' if error else '000000'
            payout.ResultMessage = error
            payout.AuthorId = homer.mangopay_user_id
            payout.Tag = str(e_id)
            Get.return_value = payout
            r = self.callback(qs)
            assert CSRF_TOKEN not in r.headers.cookie
            assert r.code == 200, r.text
            homer = homer.refetch()
            if status == 'succeeded':
                assert homer.balance == 0
                assert homer.status == 'closed'
            else:
                assert homer.balance == 10
                assert homer.status == 'active'
                emails = self.get_emails()
                assert len(emails) == 1
                assert emails[0]['to'][0] == 'homer <%s>' % homer.email
                assert 'fail' in emails[0]['subject']
            self.db.self_check()
            homer.update_status('active')  # reset for next loop run

    @patch('mangopay.resources.BankWirePayOut.get')
    @patch('mangopay.resources.Refund.get')
    def test_payout_refund_callback(self, R_Get, PO_Get):
        homer, ba = self.homer, self.homer_route
        for status in ('failed', 'succeeded'):
            # Create the payout
            self.make_exchange('mango-cc', 10, 0, homer)
            e_id = record_exchange(self.db, ba, -9, 1, 0, homer, 'pre')
            assert homer.balance == 0
            homer.close(None)
            assert homer.status == 'closed'
            payout = BankWirePayOut()
            payout.Status = 'SUCCEEDED'
            payout.ResultCode = '000000'
            payout.AuthorId = homer.mangopay_user_id
            payout.Tag = str(e_id)
            PO_Get.return_value = payout
            # Create the refund
            status_up = status.upper()
            error = 'FOO' if status == 'failed' else None
            refund = Refund()
            refund.DebitedFunds = Money(900, 'EUR')
            refund.Fees = Money(-100, 'EUR')
            refund.Status = status_up
            refund.ResultCode = '000001' if error else '000000'
            refund.ResultMessage = error
            refund.RefundReason = Reason(message='BECAUSE 42')
            refund.AuthorId = homer.mangopay_user_id
            R_Get.return_value = refund
            # Call back
            qs = "EventType=PAYOUT_REFUND_"+status_up+"&RessourceId=123456790"
            r = self.callback(qs)
            assert r.code == 200, r.text
            homer = homer.refetch()
            if status == 'failed':
                assert homer.balance == 0
                assert homer.status == 'closed'
            else:
                assert homer.balance == 10
                assert homer.status == 'active'
                emails = self.get_emails()
                assert len(emails) == 1
                assert emails[0]['to'][0] == 'homer <%s>' % homer.email
                assert 'fail' in emails[0]['subject']
                assert 'BECAUSE 42' in emails[0]['text']
            self.db.self_check()
            homer.update_status('active')  # reset for next loop run

    @patch('mangopay.resources.PayIn.get')
    def test_payin_bank_wire_callback(self, Get):
        homer = self.homer
        route = ExchangeRoute.insert(homer, 'mango-bw', 'x')
        for status in ('failed', 'succeeded'):
            status_up = status.upper()
            error = 'FOO' if status == 'failed' else None
            e_id = record_exchange(self.db, route, 11, 0, 0, homer, 'pre')
            assert homer.balance == 0
            homer.close(None)
            assert homer.status == 'closed'
            qs = "EventType=PAYIN_NORMAL_"+status_up+"&RessourceId=123456790"
            payin = BankWirePayIn()
            payin.Status = status_up
            payin.ResultCode = '000001' if error else '000000'
            payin.ResultMessage = error
            payin.AuthorId = homer.mangopay_user_id
            payin.PaymentType = 'BANK_WIRE'
            payin.DeclaredDebitedFunds = Money(1100, 'EUR')
            payin.DeclaredFees = Money(0, 'EUR')
            payin.CreditedFunds = Money(1100, 'EUR')
            payin.Tag = str(e_id)
            Get.return_value = payin
            r = self.callback(qs)
            assert r.code == 200, r.text
            homer = homer.refetch()
            if status == 'succeeded':
                assert homer.balance == 11
                assert homer.status == 'active'
            else:
                assert homer.balance == 0
                assert homer.status == 'closed'
            emails = self.get_emails()
            assert len(emails) == 1
            assert emails[0]['to'][0] == 'homer <%s>' % homer.email
            assert status[:4] in emails[0]['subject']
            self.db.self_check()
            homer.update_status('active')  # reset for next loop run

    @patch('mangopay.resources.PayIn.get')
    def test_payin_bank_wire_callback_amount_mismatch(self, Get):
        self._test_payin_bank_wire_callback_amount_mismatch(Get, 2)

    @patch('mangopay.resources.PayIn.get')
    def test_payin_bank_wire_callback_amount_and_fee_mismatch(self, Get):
        self._test_payin_bank_wire_callback_amount_mismatch(Get, 50)

    def _test_payin_bank_wire_callback_amount_mismatch(self, Get, fee):
        homer = self.homer
        route = ExchangeRoute.insert(homer, 'mango-bw', 'x')
        e_id = record_exchange(self.db, route, 11, 0, 0, homer, 'pre')
        assert homer.balance == 0
        homer.close(None)
        assert homer.status == 'closed'
        qs = "EventType=PAYIN_NORMAL_SUCCEEDED&RessourceId=123456790"
        payin = BankWirePayIn()
        payin.Status = 'SUCCEEDED'
        payin.ResultCode = '000000'
        payin.ResultMessage = None
        payin.AuthorId = homer.mangopay_user_id
        payin.PaymentType = 'BANK_WIRE'
        payin.DeclaredDebitedFunds = Money(4500, 'EUR')
        payin.DeclaredFees = Money(100, 'EUR')
        payin.DebitedFunds = Money(302, 'EUR')
        payin.Fees = Money(fee, 'EUR')
        payin.CreditedFunds = Money(302 - fee, 'EUR')
        payin.Tag = str(e_id)
        Get.return_value = payin
        r = self.callback(qs)
        assert r.code == 200, r.text
        e = self.db.one("SELECT * FROM exchanges WHERE id = %s", (e_id,))
        assert e.amount == D(payin.CreditedFunds.Amount) / D(100)
        assert e.fee == D(fee) / D(100)
        assert e.vat == D('0.01')
        assert e.status == 'succeeded'
        homer = homer.refetch()
        assert homer.balance == e.amount
        assert homer.status == 'active'
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['to'][0] == 'homer <%s>' % homer.email
        assert 'succ' in emails[0]['subject']
        self.db.self_check()
