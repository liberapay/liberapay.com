from __future__ import absolute_import, division, print_function, unicode_literals

import os
from gittip import wireup
from gittip.testing import Harness
from gittip.models.participant import Participant


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)

        self._blech = ( os.environ['CANONICAL_SCHEME']
                      , os.environ['CANONICAL_HOST']
                       )
        os.environ['CANONICAL_SCHEME'] = 'https'
        os.environ['CANONICAL_HOST'] = 'www.gittip.com'
        wireup.canonical()

    def tearDown(self):
        Harness.tearDown(self)
        os.environ['CANONICAL_SCHEME'] = self._blech[0]
        os.environ['CANONICAL_HOST'] = self._blech[1]
        wireup.canonical()


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


    def test_session_cookie_is_sent_for_http_as_well(self):
        # https://github.com/gittip/www.gittip.com/issues/940

        self.make_participant('alice')

        # Now make a request that canonizer will redirect.
        redirect = self.client.GET( "/"
                                  , auth_as='alice'
                                  , HTTP_X_FORWARDED_PROTO='http'
                                  , HTTP_HOST='www.gittip.com'
                                  , raise_immediately=False
                                   )
        assert redirect.code == 302
        assert redirect.headers.cookie['session'].value == ""

        # This is bad, because it means that the user will be signed out of
        # https://www.gittip.com/ if they make a request for
        # http://www.gittip.com/. They might do this themselves accidentally,
        # but more likely a browser plugin (such as DoNotTrack) will do it for
        # them. The way we fix this is to set "secure" on the session cookie,
        # so that the browser won't send the session cookie to the server in
        # the case of http://www.gittipcom/. Without a session cookie in the
        # request, gittip.security.authentication.outbound won't set one on the
        # way out.


    def test_session_cookie_is_secure_if_it_should_be(self):
        # https://github.com/gittip/www.gittip.com/issues/940
        response = self.client.GET( "/"
                                  , auth_as=self.make_participant('alice').username
                                  , HTTP_X_FORWARDED_PROTO='https'
                                  , HTTP_HOST='www.gittip.com'
                                   )
        assert response.code == 200
        assert '; secure' in response.headers.cookie['session'].output()
