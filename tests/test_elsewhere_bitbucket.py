from __future__ import print_function, unicode_literals

from aspen.http.request import UnicodeWithParams
from gittip.elsewhere import bitbucket
from gittip.testing import Harness


class TestElsewhereBitbucket(Harness):

    def test_get_user_info_gets_user_info(self):
        bitbucket.BitbucketAccount("1", {'username': 'alice'}).opt_in('alice')
        expected = {"username": "alice"}
        actual = bitbucket.get_user_info('alice')
        assert actual == expected

    def test_get_user_info_gets_user_info_from_UnicodeWithParams(self):
        bitbucket.BitbucketAccount("1", {'username': 'alice'}).opt_in('alice')
        expected = {"username": "alice"}
        actual = bitbucket.get_user_info(UnicodeWithParams('alice', {}))
        assert actual == expected
