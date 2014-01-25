from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.testing import Harness


class Tests(Harness):

    def test_redirect_redirects(self):
        self.make_participant('alice')
        actual = self.client.GxT('/on/bountysource/redirect', auth_as='alice').code
        assert actual == 302
