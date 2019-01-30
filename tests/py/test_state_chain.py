import json

from pando.http.request import Request
from pando.http.response import Response

from liberapay.security import csrf
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.client.website.canonical_scheme = 'https'
        self.client.website.canonical_host = 'example.com'
        self._cookie_domain = self.client.website.cookie_domain
        self.client.website.cookie_domain = '.example.com'

    def tearDown(self):
        Harness.tearDown(self)
        website = self.client.website
        website.canonical_scheme = website.env.canonical_scheme
        website.canonical_host = website.env.canonical_host
        website.cookie_domain = self._cookie_domain

    def test_canonize_canonizes(self):
        response = self.client.GxT("/",
                                   HTTP_HOST=b'example.com',
                                   HTTP_X_FORWARDED_PROTO=b'http',
                                   )
        assert response.code == 302
        assert response.headers[b'Location'] == b'https://example.com/'
        assert response.headers[b'Cache-Control'] == b'public, max-age=86400'

    def test_no_cookies_over_http(self):
        """
        We don't want to send cookies over HTTP, especially not CSRF and
        session cookies, for obvious security reasons.
        """
        alice = self.make_participant('alice')
        redirect = self.client.GET("/",
                                   auth_as=alice,
                                   HTTP_X_FORWARDED_PROTO=b'http',
                                   HTTP_HOST=b'example.com',
                                   raise_immediately=False,
                                   )
        assert redirect.code == 302
        assert not redirect.headers.cookie

    def test_early_failures_dont_break_everything(self):
        old_from_wsgi = Request.from_wsgi
        def broken_from_wsgi(*a, **kw):
            raise Response(400)
        try:
            Request.from_wsgi = classmethod(broken_from_wsgi)
            assert self.client.GET("/", raise_immediately=False).code == 400
        finally:
            Request.from_wsgi = old_from_wsgi

    def test_i18n_subdomain_works(self):
        r = self.client.GET(
            '/',
            HTTP_X_FORWARDED_PROTO=b'https', HTTP_HOST=b'fr.example.com',
            raise_immediately=False,
        )
        assert r.code == 200
        assert '<html lang="fr">' in r.text
        assert 'À propos' in r.text

    def test_i18n_subdomain_is_redirected_to_https(self):
        r = self.client.GET(
            '/',
            HTTP_X_FORWARDED_PROTO=b'http', HTTP_HOST=b'en.example.com',
            raise_immediately=False,
        )
        assert r.code == 302
        assert not r.headers.cookie
        assert r.headers[b'Location'] == b'https://en.example.com/'

    def test_csrf_cookie_properties(self):
        r = self.client.GET(
            '/',
            HTTP_X_FORWARDED_PROTO=b'https', HTTP_HOST=b'en.example.com',
            csrf_token=None, raise_immediately=False,
        )
        assert r.code == 200
        cookie = r.headers.cookie[csrf.CSRF_TOKEN]
        assert cookie['domain'] == '.example.com'
        assert cookie['expires'][-4:] == ' GMT'
        assert cookie['path'] == '/'
        assert cookie['secure'] is True
        assert cookie['samesite'] == 'lax'


class Tests2(Harness):

    def test_accept_header_is_respected(self):
        r = self.client.GET('/about/stats', HTTP_ACCEPT=b'application/json')
        assert r.headers[b'Content-Type'] == b'application/json; charset=UTF-8'
        json.loads(r.text)

    def test_error_spt_works(self):
        r = self.client.POST('/', csrf_token=False, raise_immediately=False)
        assert r.code == 403

    def test_cors_is_not_allowed_by_default(self):
        r = self.client.GET('/')
        assert b'Access-Control-Allow-Origin' not in r.headers

    def test_cors_is_allowed_for_assets(self):
        r = self.client.GET('/assets/jquery.min.js')
        assert r.code == 200
        assert r.headers[b'Access-Control-Allow-Origin'] == b'*'

    def test_caching_of_assets(self):
        r = self.client.GET('/assets/jquery.min.js')
        assert r.headers[b'Cache-Control'] == b'public, max-age=3600'
        assert b'Vary' not in r.headers
        assert not r.headers.cookie

    def test_caching_of_assets_with_etag(self):
        r = self.client.GET(self.client.website.asset('jquery.min.js'))
        assert r.headers[b'Cache-Control'] == b'public, max-age=31536000'
        assert b'Vary' not in r.headers
        assert not r.headers.cookie

    def test_caching_of_simplates(self):
        r = self.client.GET('/')
        assert r.headers[b'Cache-Control'] == b'no-cache'
        assert b'Vary' not in r.headers

    def test_no_csrf_cookie(self):
        r = self.client.POST('/', csrf_token=False, raise_immediately=False)
        assert r.code == 403
        assert "cookie" in r.text
        assert csrf.CSRF_TOKEN in r.headers.cookie

    def test_no_csrf_cookie_unknown_method_on_asset(self):
        r = self.client.hit('UNKNOWN', '/assets/base.css', csrf_token=False,
                            raise_immediately=False)
        assert r.code == 405

    def test_bad_csrf_cookie(self):
        r = self.client.POST('/', csrf_token='bad_token', raise_immediately=False)
        assert r.code == 403
        assert "The anti-CSRF tokens don't match." in r.text
        assert r.headers.cookie[csrf.CSRF_TOKEN].value != 'bad_token'

    def test_csrf_cookie_set_for_most_requests(self):
        r = self.client.GET('/')
        assert csrf.CSRF_TOKEN in r.headers.cookie

    def test_no_csrf_cookie_set_for_assets(self):
        r = self.client.GET('/assets/base.css')
        assert csrf.CSRF_TOKEN not in r.headers.cookie

    def test_reject_forgeries_accepts_good_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeeffff'
        state = self.client.GET('/', csrf_token=token, return_after='reject_forgeries', want='state')
        assert state['csrf_token'] == token

    def test_reject_forgeries_rejects_overlong_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeefffff'
        state = self.client.GET('/', csrf_token=token, return_after='reject_forgeries', want='state')
        assert state['csrf_token'] != token

    def test_reject_forgeries_rejects_underlong_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeefff'
        state = self.client.GET('/', csrf_token=token, return_after='reject_forgeries', want='state')
        assert state['csrf_token'] != token

    def test_reject_forgeries_accepts_token_with_non_base64_chars(self):
        token = 'ddddeeeeaaaadddd bbbbeeeeeeeefff'
        state = self.client.GET('/', csrf_token=token, return_after='reject_forgeries', want='state')
        assert state['csrf_token'] == token

    def test_malformed_body(self):
        r = self.client.POST('/', body=b'\0', content_type=b'application/x-www-form-urlencoded')
        assert r.code == 200

    def test_unknown_body_type(self):
        r = self.client.POST('/', body=b'x', content_type=b'unknown/x')
        assert r.code == 200

    def test_non_dict_body(self):
        r = self.client.POST('/', body=b'[]', content_type=b'application/json')
        assert r.code == 200

    def test_no_trailing_slash_redirects(self):
        r = self.client.GET('/foo', raise_immediately=False)
        assert r.code == 404, r.text

    def test_null_byte_results_in_400(self):
        r = self.client.GET('/foo%00', raise_immediately=False)
        assert r.code == 400, r.text

    def test_quoted_unicode_path_is_okay(self):
        r = self.client.GET('/about/%C3%A9', raise_immediately=False)
        assert r.code == 404, r.text
        r = self.client.GET('', PATH_INFO='/about/%C3%A9', raise_immediately=False)
        assert r.code == 404, r.text

    def test_unquoted_unicode_path_is_okay(self):
        r = self.client.GET('/about/é'.encode('utf8'), raise_immediately=False)
        assert r.code == 404, r.text
        r = self.client.GET('', PATH_INFO='/about/é', raise_immediately=False)
        assert r.code == 404, r.text

    def test_quoted_unicode_querystring_is_okay(self):
        r = self.client.GET('/', QUERY_STRING=b'%C3%A9=%C3%A9', raise_immediately=False)
        assert r.code == 200, r.text
        r = self.client.GET('/', QUERY_STRING='%C3%A9=%C3%A9', raise_immediately=False)
        assert r.code == 200, r.text

    def test_unquoted_unicode_querystring_is_okay(self):
        r = self.client.GET('/', QUERY_STRING='é=é'.encode('utf8'), raise_immediately=False)
        assert r.code == 200, r.text
        r = self.client.GET('/', QUERY_STRING='é=é', raise_immediately=False)
        assert r.code == 200, r.text
