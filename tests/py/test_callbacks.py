from __future__ import absolute_import, division, print_function, unicode_literals

from mock import patch

from mangopaysdk.entities.payout import PayOut

from liberapay.billing.exchanges import record_exchange, repr_error
from liberapay.testing.mangopay import MangopayHarness


class TestMangopayCallbacks(MangopayHarness):

    def callback(self, qs, **kw):
        kw.setdefault('raise_immediately', False)
        return self.client.GET('/callbacks/mangopay?'+qs, **kw)

    @patch('mangopaysdk.tools.apipayouts.ApiPayOuts.Get')
    @patch('liberapay.billing.exchanges.record_exchange_result')
    def test_payout_callback(self, rer, Get):
        homer, ba = self.homer, self.homer_route
        for status in ('succeeded', 'failed'):
            status_up = status.upper()
            error = 'FOO' if status == 'failed' else None
            e_id = record_exchange(self.db, ba, 10, 0, homer, 'pre')
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
            assert rer.call_count == 1
            assert rer.call_args[0][:-1] == (self.db, str(e_id), status, repr_error(payout))
            assert rer.call_args[0][-1].id == homer.id
            assert rer.call_args[1] == {}
            rer.reset_mock()
