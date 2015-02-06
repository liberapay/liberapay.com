from __future__ import absolute_import, division, print_function, unicode_literals

from base64 import b64encode

from gratipay import wireup
from gratipay.security.user import SESSION
from gratipay.testing import Harness
from environment import Environment
from aspen.http.request import Request
from aspen.http.response import Response


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Grab configuration from the environment, storing for later.
        env = wireup.env()
        self.environ = env.environ

        # Change env, doesn't change self.environ.
        env.canonical_scheme = 'https'
        env.canonical_host = 'gratipay.com'

        wireup.canonical(env)

    def tearDown(self):
        Harness.tearDown(self)
        reset = Environment(CANONICAL_SCHEME=unicode, CANONICAL_HOST=unicode, environ=self.environ)
        wireup.canonical(reset)

    def test_canonize_canonizes(self):
        response = self.client.GxT( "/"
                                  , HTTP_HOST=b'gratipay.com'
                                  , HTTP_X_FORWARDED_PROTO=b'http'
                                   )
        assert response.code == 302
        assert response.headers['Location'] == b'https://gratipay.com/'

    def test_session_cookie_isnt_overwritten_by_canonizer(self):
        # https://github.com/gratipay/gratipay.com/issues/940

        self.make_participant('alice')

        # Make a request that canonizer will redirect.
        redirect = self.client.GET( "/"
                                  , auth_as='alice'
                                  , HTTP_X_FORWARDED_PROTO=b'http'
                                  , HTTP_HOST=b'gratipay.com'
                                  , raise_immediately=False
                                   )
        assert redirect.code == 302
        assert SESSION not in redirect.headers.cookie

        # This is bad, because it means that the user will be signed out of
        # https://gratipay.com/ if they make a request for
        # http://gratipay.com/.

    def test_session_cookie_not_set_under_API_key_auth(self):
        alice = self.make_participant('alice', claimed_time='now')
        api_key = alice.recreate_api_key()

        auth_header = b'Basic ' + b64encode(b'%s:%s' % (alice.id, api_key))
        response = self.client.GET( '/alice/public.json'
                                  , HTTP_AUTHORIZATION=auth_header
                                  , HTTP_X_FORWARDED_PROTO=b'https'
                                  , HTTP_HOST=b'gratipay.com'
                                   )

        assert response.code == 200
        assert SESSION not in response.headers.cookie

    def test_old_API_key_auth(self):
        alice = self.make_participant('alice', claimed_time='now')
        api_key = alice.recreate_api_key()

        auth_header = b'Basic ' + b64encode(b'%s:' % api_key)
        response = self.client.GET( '/alice/public.json'
                                  , HTTP_AUTHORIZATION=auth_header
                                  , HTTP_X_FORWARDED_PROTO=b'https'
                                  , HTTP_HOST=b'gratipay.com'
                                   )

        assert response.code == 200

    def test_bad_userid_returns_401(self):
        self.make_participant('alice', claimed_time='now')
        auth_header = b'Basic ' + b64encode(b'foo:')
        response = self.client.GxT( '/alice/public.json'
                                  , HTTP_AUTHORIZATION=auth_header
                                  , HTTP_X_FORWARDED_PROTO=b'https'
                                  , HTTP_HOST=b'gratipay.com'
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

    def test_error_spt_works(self):
        r = self.client.POST('/', csrf_token=False, raise_immediately=False)
        assert r.code == 403
