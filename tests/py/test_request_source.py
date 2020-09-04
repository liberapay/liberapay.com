from ipaddress import IPv4Network

from liberapay.testing import Harness


class Tests(Harness):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website._trusted_proxies = getattr(cls.website, 'trusted_proxies', None)
        cls.website.trusted_proxies = [
            [IPv4Network('10.0.0.0/8')],
            [IPv4Network('141.101.64.0/18')],
        ]

    @classmethod
    def tearDownClass(cls):
        cls.website.trusted_proxies = cls.website._trusted_proxies
        super().tearDownClass()

    def request(self, forwarded_for, source, **kw):
        kw['HTTP_X_FORWARDED_FOR'] = forwarded_for
        kw['REMOTE_ADDR'] = source
        kw.setdefault('return_after', 'attach_environ_to_request')
        kw.setdefault('want', 'request')
        return self.client.GET('/', **kw)

    def test_request_source_with_invalid_header_from_trusted_proxy(self):
        r = self.request(b'f\xc3\xa9e, \t bar', b'10.0.0.1')
        assert str(r.source) == '10.0.0.1'
        assert r.bypasses_proxy is True

    def test_request_source_with_invalid_header_from_untrusted_proxy(self):
        r = self.request(b'f\xc3\xa9e, \tbar', b'8.8.8.8')
        assert str(r.source) == '8.8.8.8'
        assert r.bypasses_proxy is True

    def test_request_source_with_valid_headers_from_trusted_proxies(self):
        r = self.request(b'8.8.8.8,141.101.69.139', b'10.0.0.1')
        assert str(r.source) == '8.8.8.8'
        assert r.bypasses_proxy is False
        r = self.request(b'8.8.8.8', b'10.0.0.2')
        assert str(r.source) == '8.8.8.8'
        assert r.bypasses_proxy is True

    def test_request_source_with_valid_headers_from_untrusted_proxies(self):
        # 8.8.8.8 claims that the request came from 0.0.0.0, but we don't trust 8.8.8.8
        r = self.request(b'0.0.0.0, 8.8.8.8,141.101.69.140', b'10.0.0.1')
        assert str(r.source) == '8.8.8.8'
        assert r.bypasses_proxy is False
        r = self.request(b'0.0.0.0, 8.8.8.8', b'10.0.0.1')
        assert str(r.source) == '8.8.8.8'
        assert r.bypasses_proxy is True

    def test_request_source_with_forged_headers_from_untrusted_client(self):
        # 8.8.8.8 claims that the request came from a trusted proxy, but we don't trust 8.8.8.8
        r = self.request(b'0.0.0.0,141.101.69.141, 8.8.8.8,141.101.69.142', b'10.0.0.1')
        assert str(r.source) == '8.8.8.8'
        assert r.bypasses_proxy is False
        r = self.request(b'0.0.0.0, 141.101.69.143, 8.8.8.8', b'10.0.0.1')
        assert str(r.source) == '8.8.8.8'
        assert r.bypasses_proxy is True
