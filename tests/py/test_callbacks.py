from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

from mock import patch

from mangopay.resources import BankWirePayOut, BankWirePayIn, Dispute, PayIn, Refund
from mangopay.utils import Reason

from liberapay.billing.payday import Payday
from liberapay.billing.transactions import Money, record_exchange
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.security.csrf import CSRF_TOKEN
from liberapay.testing.emails import EmailHarness
from liberapay.testing.mangopay import fake_transfer, FakeTransfersHarness, MangopayHarness
from liberapay.utils import utcnow


class TestMangopayCallbacks(EmailHarness, FakeTransfersHarness, MangopayHarness):

    def callback(self, qs, **kw):
        kw.setdefault('HTTP_ACCEPT', b'application/json')
        kw.setdefault('raise_immediately', False)
        return self.client.GET('/callbacks/mangopay?'+qs, **kw)

    @patch('mangopay.resources.Dispute.get')
    @patch('mangopay.resources.PayIn.get')
    @patch('mangopay.resources.SettlementTransfer.save', autospec=True)
    def test_dispute_callback_lost(self, save, get_payin, get_dispute):
        self.make_participant(
            'LiberapayOrg', kind='organization', balance=D('100.00'),
            mangopay_user_id='0', mangopay_wallet_id='0',
        )
        save.side_effect = fake_transfer
        e_id = self.make_exchange('mango-cc', D('16'), D('1'), self.janet)
        dispute = Dispute()
        dispute.Id = '-1'
        dispute.CreationDate = utcnow()
        dispute.DisputedFunds = Money(1700, 'EUR')
        dispute.DisputeType = 'CONTESTABLE'
        dispute.InitialTransactionType = 'PAYIN'
        get_dispute.return_value = dispute
        payin = PayIn(tag=str(e_id))
        get_payin.return_value = payin
        # Transfer some of the money to homer
        self.janet.set_tip_to(self.homer, D('3.68'))
        Payday.start().run()
        # Withdraw some of the money
        self.make_exchange('mango-ba', D('-2.68'), 0, self.homer)
        # Add a bit of money that will remain undisputed, to test bundle swapping
        self.make_exchange('mango-cc', D('0.32'), 0, self.janet)
        self.make_exchange('mango-cc', D('0.55'), 0, self.homer)
        # Call back
        self.db.self_check()
        for status in ('CREATED', 'CLOSED'):
            dispute.Status = status
            if status == 'CLOSED':
                dispute.ResultCode = 'LOST'
            qs = "EventType=DISPUTE_"+status+"&RessourceId=123456790"
            r = self.callback(qs, raise_immediately=True)
            assert r.code == 200, r.text
            self.db.self_check()
        # Check final state
        balances = dict(self.db.all("SELECT username, balance FROM participants"))
        assert balances == {
            '_chargebacks_': D('16.00'),
            'david': 0,
            'homer': 0,
            'janet': 0,
            'LiberapayOrg': D('98.19'),
        }
        debts = dict(((r[0], r[1]), r[2]) for r in self.db.all("""
            SELECT p_debtor.username AS debtor, p_creditor.username AS creditor, sum(d.amount)
              FROM debts d
              JOIN participants p_debtor ON p_debtor.id = d.debtor
              JOIN participants p_creditor ON p_creditor.id = d.creditor
             WHERE d.status = 'due'
          GROUP BY p_debtor.username, p_creditor.username
        """))
        assert debts == {
            ('janet', 'LiberapayOrg'): D('1.00'),
            ('janet', 'homer'): D('3.36'),
            ('homer', 'LiberapayOrg'): D('1.81'),
        }

    @patch('mangopay.resources.Dispute.get')
    @patch('mangopay.resources.PayIn.get')
    @patch('mangopay.resources.SettlementTransfer.save', autospec=True)
    def test_dispute_callback_won(self, save, get_payin, get_dispute):
        self.make_participant('LiberapayOrg', kind='organization')
        save.side_effect = fake_transfer
        e_id = self.make_exchange('mango-cc', D('16'), D('1'), self.janet)
        dispute = Dispute()
        dispute.Id = '-1'
        dispute.CreationDate = utcnow()
        dispute.DisputedFunds = Money(1700, 'EUR')
        dispute.DisputeType = 'CONTESTABLE'
        dispute.InitialTransactionType = 'PAYIN'
        get_dispute.return_value = dispute
        payin = PayIn(tag=str(e_id))
        get_payin.return_value = payin
        # Transfer some of the money to homer
        self.janet.set_tip_to(self.homer, D('3.68'))
        Payday.start().run()
        # Withdraw some of the money
        self.make_exchange('mango-ba', D('-2.68'), 0, self.homer)
        # Add money that will remain undisputed, to test bundle swapping
        self.make_exchange('mango-cc', D('2.69'), 0, self.janet)
        # Call back
        self.db.self_check()
        for status in ('CREATED', 'CLOSED'):
            dispute.Status = status
            if status == 'CLOSED':
                dispute.ResultCode = 'WON'
            qs = "EventType=DISPUTE_"+status+"&RessourceId=123456790"
            r = self.callback(qs)
            assert r.code == 200, r.text
            self.db.self_check()
        # Check final state
        disputed = self.db.all("SELECT * FROM cash_bundles WHERE disputed")
        debts = self.db.all("SELECT * FROM debts")
        assert not disputed
        assert not debts
        balances = dict(self.db.all("SELECT username, balance FROM participants"))
        assert balances == {
            'david': 0,
            'homer': D('1.00'),
            'janet': D('15.01'),
            'LiberapayOrg': 0,
        }

    @patch('mangopay.resources.BankWirePayOut.get')
    def test_payout_callback(self, Get):
        homer, ba = self.homer, self.homer_route
        for status in ('succeeded', 'failed'):
            status_up = status.upper()
            error = 'FOO' if status == 'failed' else None
            self.make_exchange('mango-cc', 10, 0, homer)
            e_id = record_exchange(self.db, ba, -10, 0, 0, homer, 'pre').id
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
            e_id = record_exchange(self.db, ba, -9, 1, 0, homer, 'pre').id
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
        cases = (
            ('failed', '000001', 'FOO'),
            ('failed', '101109', 'The payment period has expired'),
            ('succeeded', '000000', None),
        )
        for status, result_code, error in cases:
            status_up = status.upper()
            e_id = record_exchange(self.db, route, 11, 0, 0, homer, 'pre').id
            assert homer.balance == 0
            homer.close(None)
            assert homer.status == 'closed'
            qs = "EventType=PAYIN_NORMAL_"+status_up+"&RessourceId=123456790"
            payin = BankWirePayIn()
            payin.Status = status_up
            payin.ResultCode = result_code
            payin.ResultMessage = error
            payin.AuthorId = homer.mangopay_user_id
            payin.PaymentType = 'BANK_WIRE'
            payin.DeclaredDebitedFunds = Money(1100, 'EUR')
            payin.DeclaredFees = Money(0, 'EUR')
            payin.CreditedFunds = Money(0, 'XXX') if error else Money(1100, 'EUR')
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
            expected = 'expired' if result_code == '101109' else status[:4]
            assert expected in emails[0]['subject']
            self.db.self_check()
            homer.update_status('active')  # reset for next loop run

    @patch('mangopay.resources.PayIn.get')
    def test_payin_bank_wire_callback_unexpected(self, Get):
        homer = self.homer
        cases = (
            ('failed', '000001', 'FOO', 0),
            ('succeeded', '000000', None, 5),
            ('succeeded', '000000', None, 2),
        )
        for status, result_code, error, fee in cases:
            status_up = status.upper()
            homer.set_tip_to(self.janet, D('1.00'))
            homer.close('downstream')
            assert homer.balance == 0
            assert homer.status == 'closed'
            qs = "EventType=PAYIN_NORMAL_"+status_up+"&RessourceId=123456790"
            payin = BankWirePayIn()
            payin.Status = status_up
            payin.ResultCode = result_code
            payin.ResultMessage = error
            payin.AuthorId = homer.mangopay_user_id
            payin.PaymentType = 'BANK_WIRE'
            payin.DebitedFunds = Money(242, 'EUR')
            payin.DeclaredDebitedFunds = payin.DebitedFunds
            payin.DeclaredFees = Money(fee, 'EUR')
            payin.Fees = Money(fee, 'EUR')
            payin.CreditedFunds = Money(0, 'XXX') if error else Money(242 - fee, 'EUR')
            payin.CreditedWalletId = homer.mangopay_wallet_id
            Get.return_value = payin
            r = self.callback(qs)
            assert r.code == 200, r.text
            amount = D(242 - fee) / D(100)
            e = self.db.one("SELECT * FROM exchanges ORDER BY timestamp DESC lIMIT 1")
            assert e.status == status
            assert e.amount == amount
            assert e.fee == D(fee) / D(100)
            homer = homer.refetch()
            if status == 'succeeded':
                assert homer.balance == amount
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
        e_id = record_exchange(self.db, route, 11, 0, 0, homer, 'pre').id
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
