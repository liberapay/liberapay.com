from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.testing import Harness


class TestBalancedCallbacks(Harness):

    def callback(self, *a, **kw):
        kw.setdefault(b'HTTP_X_FORWARDED_FOR', b'50.18.199.26')
        kw.setdefault('content_type', 'application/json')
        kw.setdefault('raise_immediately', False)
        return self.client.POST('/balanced-callbacks', **kw)

    def test_simplate_checks_source_address(self):
        r = self.callback(HTTP_X_FORWARDED_FOR=b'0.0.0.0')
        assert r.code == 403

    def test_simplate_doesnt_require_a_csrf_token(self):
        r = self.callback(body=b'{"events": []}', csrf_token=False)
        assert r.code == 200, r.body
