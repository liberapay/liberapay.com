from __future__ import absolute_import, division, print_function, unicode_literals

import json

from mock import patch

from gratipay.billing.exchanges import record_exchange
from gratipay.models.exchange_route import ExchangeRoute
from gratipay.testing import Harness


class TestBalancedCallbacks(Harness):

    def callback(self, *a, **kw):
        kw.setdefault(b'HTTP_X_FORWARDED_FOR', b'50.18.199.26')
        kw.setdefault('content_type', 'application/json')
        kw.setdefault('raise_immediately', False)
        return self.client.POST('/callbacks/balanced', **kw)

    def test_simplate_checks_source_address(self):
        r = self.callback(HTTP_X_FORWARDED_FOR=b'0.0.0.0')
        assert r.code == 403

    def test_simplate_doesnt_require_a_csrf_token(self):
        r = self.callback(body=b'{"events": []}', csrf_token=False)
        assert r.code == 200, r.body

    def test_no_csrf_cookie_set_for_callbacks(self):
        r = self.callback(body=b'{"events": []}', csrf_token=False)
        assert b'csrf_token' not in r.headers.cookie

    @patch('gratipay.billing.exchanges.record_exchange_result')
    def test_credit_callback(self, rer):
        alice = self.make_participant('alice', last_ach_result='')
        ba = ExchangeRoute.from_network(alice, 'balanced-ba')
        for status in ('succeeded', 'failed'):
            error = 'FOO' if status == 'failed' else None
            e_id = record_exchange(self.db, ba, 10, 0, alice, 'pre')
            body = json.dumps({
                "events": [
                    {
                        "type": "credit."+status,
                        "entity": {
                            "credits": [
                                {
                                    "failure_reason": error,
                                    "meta": {
                                        "participant_id": alice.id,
                                        "exchange_id": e_id,
                                    },
                                    "status": status,
                                }
                            ]
                        }
                    }
                ]
            })
            r = self.callback(body=body, csrf_token=False)
            assert r.code == 200, r.body
            assert rer.call_count == 1
            assert rer.call_args[0][:-1] == (self.db, e_id, status, error)
            assert rer.call_args[0][-1].id == alice.id
            assert rer.call_args[1] == {}
            rer.reset_mock()
