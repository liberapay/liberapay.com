from __future__ import absolute_import, division, print_function, unicode_literals

from base64 import b64encode
import json

from aspen.http.request import Request
from aspen.http.response import Response
from environment import Environment

from liberapay import wireup
from liberapay.constants import SESSION
from liberapay.security import csrf
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Grab configuration from the environment, storing for later.
        env = wireup.env()
        self.environ = env.environ

        # Change env, doesn't change self.environ.
        env.canonical_scheme = 'https'
        env.canonical_host = 'example.com'

        wireup.canonical(env)

    def tearDown(self):
        Harness.tearDown(self)
        reset = Environment(CANONICAL_SCHEME=str, CANONICAL_HOST=str, environ=self.environ)
        wireup.canonical(reset)

    def test_canonize_canonizes(self):
        response = self.client.GxT( "/"
                                  , HTTP_HOST=b'example.com'
                                  , HTTP_X_FORWARDED_PROTO=b'http'
                                   )
        assert response.code == 302
        assert response.headers['Location'] == b'https://example.com/'

    def test_no_cookies_over_http(self):
        """
        We don't want to send cookies over HTTP, especially not CSRF and
        session cookies, for obvious security reasons.
        """
        alice = self.make_participant('alice')
        redirect = self.client.GET( "/"
                                  , auth_as=alice
                                  , HTTP_X_FORWARDED_PROTO=b'http'
                                  , HTTP_HOST=b'example.com'
                                  , raise_immediately=False
                                   )
        assert redirect.code == 302
        assert not redirect.headers.cookie

    def test_session_cookie_not_set_under_basic_auth(self):
        alice = self.make_participant('alice')
        password = 'password'
        alice.update_password(password)

        auth_header = b'Basic ' + b64encode(b'%s:%s' % (alice.id, password))
        response = self.client.GET( '/alice/public.json'
                                  , HTTP_AUTHORIZATION=auth_header
                                  , HTTP_X_FORWARDED_PROTO=b'https'
                                  , HTTP_HOST=b'example.com'
                                   )

        assert response.code == 200
        assert SESSION not in response.headers.cookie

    def test_bad_userid_returns_401(self):
        self.make_participant('alice')
        auth_header = b'Basic ' + b64encode(b'foo:')
        response = self.client.GxT( '/alice/public.json'
                                  , HTTP_AUTHORIZATION=auth_header
                                  , HTTP_X_FORWARDED_PROTO=b'https'
                                  , HTTP_HOST=b'example.com'
                                   )
        assert response.code == 401

    def test_early_failures_dont_break_everything(self):
        old_from_wsgi = Request.from_wsgi
        def broken_from_wsgi(*a, **kw):
            raise Response(400)
        try:
            Request.from_wsgi = classmethod(broken_from_wsgi)
            assert self.client.GET("/", raise_immediately=False).code == 400
        finally:
            Request.from_wsgi = old_from_wsgi


class Tests2(Harness):

    def test_accept_header_is_respected(self):
        r = self.client.GET('/about/stats', HTTP_ACCEPT=b'application/json')
        assert r.headers['Content-Type'].startswith('application/json')
        json.loads(r.body)

    def test_error_spt_works(self):
        r = self.client.POST('/', csrf_token=False, raise_immediately=False)
        assert r.code == 403

    def test_caching_of_assets(self):
        r = self.client.GET('/assets/jquery.min.js')
        assert r.headers['Access-Control-Allow-Origin'] == 'https://liberapay.com'
        assert r.headers['Cache-Control'] == 'public, max-age=5'
        assert 'Vary' not in r.headers
        assert not r.headers.cookie

    def test_caching_of_assets_with_etag(self):
        r = self.client.GET(self.client.website.asset('jquery.min.js'))
        assert r.headers['Access-Control-Allow-Origin'] == 'https://liberapay.com'
        assert r.headers['Cache-Control'] == 'public, max-age=31536000'
        assert 'Vary' not in r.headers
        assert not r.headers.cookie

    def test_caching_of_simplates(self):
        r = self.client.GET('/')
        assert r.headers['Cache-Control'] == 'no-cache'
        assert 'Vary' not in r.headers

    def test_no_csrf_cookie(self):
        r = self.client.POST('/', csrf_token=False, raise_immediately=False)
        assert r.code == 403
        assert "Bad CSRF cookie" in r.text
        assert b'csrf_token' in r.headers.cookie

    def test_bad_csrf_cookie(self):
        r = self.client.POST('/', csrf_token=b'bad_token', raise_immediately=False)
        assert r.code == 403
        assert "Bad CSRF cookie" in r.text
        assert r.headers.cookie[b'csrf_token'].value != 'bad_token'

    def test_csrf_cookie_set_for_most_requests(self):
        r = self.client.GET('/')
        assert b'csrf_token' in r.headers.cookie

    def test_no_csrf_cookie_set_for_assets(self):
        r = self.client.GET('/assets/base.css')
        assert b'csrf_token' not in r.headers.cookie

    def test_sanitize_token_passes_through_good_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeeffff'
        assert csrf._sanitize_token(token) == token

    def test_sanitize_token_rejects_overlong_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeefffff'
        assert csrf._sanitize_token(token) is None

    def test_sanitize_token_rejects_underlong_token(self):
        token = 'ddddeeeeaaaaddddbbbbeeeeeeeefff'
        assert csrf._sanitize_token(token) is None

    def test_sanitize_token_rejects_goofy_token(self):
        token = 'ddddeeeeaaaadddd bbbbeeeeeeeefff'
        assert csrf._sanitize_token(token) is None
