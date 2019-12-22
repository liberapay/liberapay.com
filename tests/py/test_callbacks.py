from os.path import abspath
from unittest.mock import patch

from mangopay.resources import BankWirePayOut, Dispute, PayIn, Refund
from mangopay.utils import Reason

from liberapay.billing.transactions import Money, record_exchange, transfer
from liberapay.security.csrf import CSRF_TOKEN
from liberapay.testing import EUR
from liberapay.testing.emails import EmailHarness
from liberapay.testing.mangopay import fake_transfer, FakeTransfersHarness, MangopayHarness
from liberapay.utils import utcnow


class TestMangopayCallbacks(EmailHarness, FakeTransfersHarness, MangopayHarness):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website.request_processor.resources.cache.pop(abspath('www/callbacks/mangopay.spt'), None)
        cls.cwp_patch = patch('liberapay.billing.transactions.check_wallet_balance')
        cls.cwp_patch.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.cwp_patch.__exit__()
        super().tearDownClass()

    def callback(self, qs, **kw):
        kw.setdefault('HTTP_ACCEPT', b'application/json')
        kw.setdefault('raise_immediately', False)
        return self.client.GET('/callbacks/mangopay?'+qs, **kw)

    @patch('mangopay.resources.Dispute.get')
    @patch('mangopay.resources.PayIn.get')
    @patch('mangopay.resources.SettlementTransfer.save', autospec=True)
    def test_dispute_callback_lost(self, save, get_payin, get_dispute):
        self.make_participant(
            'LiberapayOrg', kind='organization', balance=EUR('100.00'),
            mangopay_user_id='0', mangopay_wallet_id='0',
        )
        save.side_effect = fake_transfer
        e_id = self.make_exchange('mango-cc', EUR('16'), EUR('1'), self.janet)
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
        transfer(self.db, self.janet.id, self.homer.id, EUR('3.68'), 'tip')
        # Withdraw some of the money
        self.make_exchange('mango-ba', EUR('-2.68'), 0, self.homer)
        # Add a bit of money that will remain undisputed, to test bundle swapping
        self.make_exchange('mango-cc', EUR('0.32'), 0, self.janet)
        self.make_exchange('mango-cc', EUR('0.55'), 0, self.homer)
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
            '_chargebacks_': EUR('16.00'),
            'david': 0,
            'homer': 0,
            'janet': 0,
            'LiberapayOrg': EUR('98.19'),
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
            ('janet', 'LiberapayOrg'): EUR('1.00'),
            ('janet', 'homer'): EUR('3.36'),
            ('homer', 'LiberapayOrg'): EUR('1.81'),
        }

    @patch('mangopay.resources.Dispute.get')
    @patch('mangopay.resources.PayIn.get')
    @patch('mangopay.resources.SettlementTransfer.save', autospec=True)
    def test_dispute_callback_won(self, save, get_payin, get_dispute):
        self.make_participant('LiberapayOrg', kind='organization')
        save.side_effect = fake_transfer
        e_id = self.make_exchange('mango-cc', EUR('16'), EUR('1'), self.janet)
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
        transfer(self.db, self.janet.id, self.homer.id, EUR('3.68'), 'tip')
        # Withdraw some of the money
        self.make_exchange('mango-ba', EUR('-2.68'), 0, self.homer)
        # Add money that will remain undisputed, to test bundle swapping
        self.make_exchange('mango-cc', EUR('2.69'), 0, self.janet)
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
            'homer': EUR('1.00'),
            'janet': EUR('15.01'),
            'LiberapayOrg': 0,
        }

    @patch('mangopay.resources.BankWirePayOut.get')
    def test_payout_callback(self, Get):
        homer, ba = self.homer, self.homer_route
        for status in ('succeeded', 'failed'):
            status_up = status.upper()
            error = 'FOO' if status == 'failed' else None
            self.make_exchange('mango-cc', 10, 0, homer)
            e_id = record_exchange(self.db, ba, EUR(-10), EUR(0), EUR(0), homer, 'pre').id
            assert homer.balance == 0
            homer.close(None)
            assert homer.status == 'closed'
            qs = "EventType=PAYOUT_NORMAL_"+status_up+"&RessourceId=123456790"
            payout = BankWirePayOut(Id=-1)
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
            e_id = record_exchange(self.db, ba, EUR(-9), EUR(1), EUR(0), homer, 'pre').id
            assert homer.balance == 0
            homer.close(None)
            assert homer.status == 'closed'
            payout = BankWirePayOut(Id=-1)
            payout.Status = 'SUCCEEDED'
            payout.ResultCode = '000000'
            payout.AuthorId = homer.mangopay_user_id
            payout.Tag = str(e_id)
            PO_Get.return_value = payout
            # Create the refund
            status_up = status.upper()
            error = 'FOO' if status == 'failed' else None
            refund = Refund(Id=-1)
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
