import os
from gittip import wireup
from gittip.testing import Harness
from gittip.testing.client import TestClient


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
