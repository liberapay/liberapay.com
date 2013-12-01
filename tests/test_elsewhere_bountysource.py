from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.testing import Harness
from gittip.testing.client import TestClient


class Tests(Harness):

    def test_redirect_redirects(self):
        self.make_participant('alice')
        actual = TestClient().get('/on/bountysource/redirect', user='alice').code
        assert actual == 302
