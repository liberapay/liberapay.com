from __future__ import absolute_import, division, print_function, unicode_literals

from mock import patch

from mangopaysdk.entities.payout import PayOut

from liberapay.billing.exchanges import record_exchange
from liberapay.testing.emails import EmailHarness
from liberapay.testing.mangopay import MangopayHarness


class TestMangopayCallbacks(EmailHarness, MangopayHarness):

    def callback(self, qs, **kw):
        kw.setdefault('raise_immediately', False)
        return self.client.GET('/callbacks/mangopay?'+qs, **kw)

    @patch('mangopaysdk.tools.apipayouts.ApiPayOuts.Get')
    def test_payout_callback(self, Get):
        homer, ba = self.homer, self.homer_route
        for status in ('succeeded', 'failed'):
            status_up = status.upper()
            error = 'FOO' if status == 'failed' else None
            self.make_exchange('mango-cc', 10, 0, homer)
            e_id = record_exchange(self.db, ba, -10, 0, homer, 'pre')
            assert homer.balance == 0
            homer.close(None)
            assert homer.status == 'closed'
            qs = "EventType=PAYOUT_NORMAL_"+status_up+"&RessourceId=123456790"
            payout = PayOut()
            payout.Status = status_up
            payout.ResultCode = '000001' if error else '000000'
            payout.ResultMessage = error
            payout.AuthorId = homer.mangopay_user_id
            payout.Tag = str(e_id)
            Get.return_value = payout
            r = self.callback(qs, csrf_token=False)
            assert b'csrf_token' not in r.headers.cookie
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
                assert emails[0]['to'][0]['email'] == homer.email
                assert 'fail' in emails[0]['subject']
            homer.update_status('active')  # reset for next loop run
