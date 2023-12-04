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
        self._dot_canonical_host = self.client.website.dot_canonical_host
        self.client.website.dot_canonical_host = '.example.com'
        self._cookie_domain = self.client.website.cookie_domain
        self.client.website.cookie_domain = '.example.com'

    def tearDown(self):
        Harness.tearDown(self)
        website = self.client.website
        website.canonical_scheme = website.env.canonical_scheme
        website.canonical_host = website.env.canonical_host
        website.dot_canonical_host = self._dot_canonical_host
        website.cookie_domain = self._cookie_domain

    def test_canonize_canonizes(self):
        response = self.client.GxT("/",
                                   HTTP_HOST=b'example.com',
                                   HTTP_X_FORWARDED_PROTO=b'http',
                                   )
        assert response.code == 302
        assert response.headers[b'Location'] == b'https://example.com/'

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

    def test_i18n_subdomains_work(self):
        r = self.client.GET(
            '/',
            HTTP_X_FORWARDED_PROTO=b'https', HTTP_HOST=b'fr.example.com',
            raise_immediately=False,
        )
        assert r.code == 200
        assert '<html lang="fr">' in r.text
        assert 'À propos' in r.text
        alice = self.make_participant('alice')
        alice.upsert_statement('zh', "歡迎，", 'profile')
        r = self.client.GET(
            '/alice',
            HTTP_X_FORWARDED_PROTO=b'https', HTTP_HOST=b'zh.example.com',
            HTTP_CF_IPCOUNTRY=b'TW',
            raise_immediately=False,
        )
        assert r.code == 200
        html = r.html_tree
        assert html.attrib["lang"] == "zh-hant-tw"
        statement_section = html.find(".//{*}section[@lang='zh']")
        assert len(statement_section) > 0, r.text
        assert statement_section[0].text == "歡迎，"
        r = self.client.GET(
            '/alice',
            HTTP_X_FORWARDED_PROTO=b'https', HTTP_HOST=b'zh-hans.example.com',
            raise_immediately=False,
        )
        assert r.code == 200
        html = r.html_tree
        assert html.attrib["lang"] == "zh-hans"
        statement_section = html.find(".//{*}section[@lang='zh-hans']")
        assert len(statement_section) > 0, r.text
        assert statement_section[0].text == "欢迎，"

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
            '/log-in',
            HTTP_X_FORWARDED_PROTO=b'https', HTTP_HOST=b'en.example.com',
            csrf_token=None, raise_immediately=False,
        )
        assert r.code == 200, r.text
        cookie = r.headers.cookie[csrf.CSRF_TOKEN]
        assert len(cookie.value) == 32
        assert cookie['domain'] == '.example.com'
        assert cookie['expires'][-4:] == ' GMT'
        assert cookie['path'] == '/'
        assert cookie['secure'] is True
        assert cookie['samesite'] == 'lax'


class Tests2(Harness):

    def test_accept_header_is_respected(self):
        r = self.client.GET('/about/paydays', HTTP_ACCEPT=b'application/json')
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
        url = self.client.website.asset('jquery.min.js')
        assert url.startswith('http://localhost/assets/jquery.min.js?etag=')
        r = self.client.GET(url[len('http://localhost'):])
        assert r.headers[b'Cache-Control'] == b'public, max-age=31536000, immutable'
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
        assert csrf.CSRF_TOKEN not in r.headers.cookie

    def test_no_csrf_cookie_unknown_method_on_asset(self):
        r = self.client.hit('UNKNOWN', '/assets/base.css', csrf_token=False,
                            raise_immediately=False)
        assert r.code == 403

    def test_csrf_cookie_mismatch(self):
        r = self.client.POST('/', {'csrf_token': 'a'*32}, csrf_token='b'*32, raise_immediately=False)
        assert r.code == 403
        assert "The anti-CSRF tokens don't match." in r.text

    def test_csrf_cookie_set_for_log_in_page(self):
        r = self.client.GET('/log-in')
        assert csrf.CSRF_TOKEN in r.headers.cookie

    def test_csrf_cookie_set_in_LoginRequired_response(self):
        r = self.client.GET('/~1/giving/', raise_immediately=False)
        assert r.code == 403
        assert csrf.CSRF_TOKEN in r.headers.cookie

    def test_no_csrf_cookie_set_for_homepage(self):
        r = self.client.GET('/')
        assert csrf.CSRF_TOKEN not in r.headers.cookie

    def test_no_csrf_cookie_set_for_assets(self):
        r = self.client.GET('/assets/base.css')
        assert csrf.CSRF_TOKEN not in r.headers.cookie

    def test_CSRF_Token_accepts_good_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeeffff'
        state = self.client.GET('/log-in', csrf_token=token, want='state')
        assert state['csrf_token'] == token
        assert token in state['response'].text

    def test_CSRF_Token_rejects_overlong_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeefffff'
        state = self.client.GET('/log-in', csrf_token=token, want='state')
        assert state['csrf_token']
        assert state['csrf_token'] != token

    def test_CSRF_Token_rejects_underlong_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeefff'
        state = self.client.GET('/log-in', csrf_token=token, want='state')
        assert state['csrf_token']
        assert state['csrf_token'] != token

    def test_CSRF_Token_accepts_token_with_non_base64_chars(self):
        token = 'ddddeeeeaaaadddd bbbbeeeeeeeefff'
        state = self.client.GET('/log-in', csrf_token=token, want='state')
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
        r = self.client.GET('', PATH_INFO='/about/%C3%A9', raise_immediately=False)
        assert r.code == 404, r.text

    def test_unquoted_unicode_path_is_okay(self):
        path = '/about/é'.encode('utf8').decode('latin1')
        r = self.client.GET('', PATH_INFO=path, raise_immediately=False)
        assert r.code == 404, r.text

    def test_quoted_unicode_querystring_is_okay(self):
        r = self.client.GET('/', QUERY_STRING='%C3%A9=%C3%A9', raise_immediately=False)
        assert r.code == 200, r.text

    def test_unquoted_unicode_querystring_is_okay(self):
        qs = 'é=é'.encode('utf8').decode('latin1')
        r = self.client.GET('/', QUERY_STRING=qs, raise_immediately=False)
        assert r.code == 200, r.text
