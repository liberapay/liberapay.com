from __future__ import absolute_import, division, print_function, unicode_literals

import os
from gittip import wireup
from gittip.testing import Harness
from gittip.testing.client import TestClient
from gittip.models.participant import Participant


class TestCanonizer(Harness):

    def setUp(self):
        self.client = TestClient()
        Harness.setUp(self)

        self._blech = ( os.environ['CANONICAL_SCHEME']
                      , os.environ['CANONICAL_HOST']
                       )
        os.environ['CANONICAL_SCHEME'] = 'https'
        os.environ['CANONICAL_HOST'] = 'www.gittip.com'
        wireup.canonical()

    def tearDown(self):
        os.environ['CANONICAL_SCHEME'] = self._blech[0]
        os.environ['CANONICAL_HOST'] = self._blech[1]
        wireup.canonical()


    def test_canonize_canonizes(self):
        response = self.client.get("/", HTTP_HOST='www.gittip.com', HTTP_X_FORWARDED_PROTO='http')
        assert response.code == 302
        assert response.headers['Location'] == 'https://www.gittip.com/'

    def test_canonize_doesnt_mess_up_auth(self):
        # https://github.com/gittip/www.gittip.com/issues/940

        self.make_participant('alice')

        # Make a normal authenticated request.
        normal = self.client.get( "/"
                                , user='alice'
                                , HTTP_X_FORWARDED_PROTO='https'
                                , HTTP_HOST='www.gittip.com'
                                 )
        alice = Participant.from_username('alice')
        assert normal.headers.cookie['session'].value == alice.session_token

        # Now make a request that canonizer will redirect.
        redirect = self.client.get( "/"
                                  , user='alice'
                                  , HTTP_X_FORWARDED_PROTO='http'
                                  , HOST='www.gittip.com'
                                   )
        assert 'session' not in redirect.headers.cookie
