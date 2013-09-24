from __future__ import absolute_import, division, print_function, unicode_literals

from gittip import wireup
from gittip.testing import Harness
from gittip.models.participant import Participant
from environment import Environment


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        # Grab configuration from the environment, storing for later.
        env = wireup.env()
        self.environ = env.environ

        # Change env, doesn't change self.environ.
        env.canonical_scheme = 'https'
        env.canonical_host = 'www.gittip.com'

        wireup.canonical(env)

    def tearDown(self):
        Harness.tearDown(self)
        reset = Environment(CANONICAL_SCHEME=unicode, CANONICAL_HOST=unicode, environ=self.environ)
        wireup.canonical(reset)


    def test_canonize_canonizes(self):
        response = self.client.GxT( "/"
                                  , HTTP_HOST='www.gittip.com'
                                  , HTTP_X_FORWARDED_PROTO='http'
                                   )
        assert response.code == 302
        assert response.headers['Location'] == 'https://www.gittip.com/'


    def test_session_cookie_set_in_auth_response(self):
        self.make_participant('alice')

        # Make a normal authenticated request.
        normal = self.client.GET( "/"
                                , auth_as='alice'
                                , HTTP_X_FORWARDED_PROTO='https'
                                , HTTP_HOST='www.gittip.com'
                                 )
        alice = Participant.from_username('alice')
        assert normal.headers.cookie['session'].value == alice.session_token


    def test_session_cookie_isnt_overwritten_by_canonizer(self):
        # https://github.com/gittip/www.gittip.com/issues/940

        self.make_participant('alice')

        # Make a request that canonizer will redirect.
        redirect = self.client.GET( "/"
                                  , auth_as='alice'
                                  , HTTP_X_FORWARDED_PROTO='http'
                                  , HTTP_HOST='www.gittip.com'
                                  , raise_immediately=False
                                   )
        assert redirect.code == 302
        assert 'session' not in redirect.headers.cookie

        # This is bad, because it means that the user will be signed out of
        # https://www.gittip.com/ if they make a request for
        # http://www.gittip.com/.


    def test_session_cookie_is_secure_if_it_should_be(self):
        # https://github.com/gittip/www.gittip.com/issues/940
        response = self.client.GET( "/"
                                  , auth_as=self.make_participant('alice').username
                                  , HTTP_X_FORWARDED_PROTO='https'
                                  , HTTP_HOST='www.gittip.com'
                                   )
        assert response.code == 200
        assert '; secure' in response.headers.cookie['session'].output()


    def test_session_cookie_not_set_under_API_key_auth(self):
        alice = self.make_participant('alice', claimed_time='now')
        api_key = alice.recreate_api_key()

        auth_header = ('Basic ' + (api_key + ':').encode('base64')).strip()
        response = self.client.GET( '/alice/public.json'
                                  , HTTP_AUTHORIZATION=auth_header
                                  , HTTP_X_FORWARDED_PROTO='https'
                                  , HTTP_HOST='www.gittip.com'
                                   )

        assert response.code == 200
        assert 'session' not in response.headers.cookie
