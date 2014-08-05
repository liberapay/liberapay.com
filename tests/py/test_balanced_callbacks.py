from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.testing import Harness


class TestBalancedCallbacks(Harness):

    def test_simplate_checks_source_address(self):
        r = self.client.PxST('/balanced-callbacks', HTTP_X_FORWARDED_FOR=b'0.0.0.0')
        assert r.code == 403
