from __future__ import absolute_import, division, print_function, unicode_literals

from aspen.http.response import Response
from gittip import utils
from gittip.testing import Harness


class Tests(Harness):

    def test_get_participant_gets_participant(self):
        expected = self.make_participant('alice', claimed_time='now')
        request = self.client.GET( '/alice/'
                                 , return_after='dispatch_request_to_filesystem'
                                 , want='request'
                                  )
        actual = utils.get_participant(request, restrict=False)
        assert actual == expected

    def test_get_participant_canonicalizes(self):
        self.make_participant('alice', claimed_time='now')
        request = self.client.GET( '/Alice/'
                                 , return_after='dispatch_request_to_filesystem'
                                 , want='request'
                                  )

        with self.assertRaises(Response) as cm:
            utils.get_participant(request, restrict=False)
        actual = cm.exception.code

        assert actual == 302

    def test_dict_to_querystring_converts_dict_to_querystring(self):
        expected = "?foo=bar"
        actual = utils.dict_to_querystring({"foo": ["bar"]})
        assert actual == expected

    def test_dict_to_querystring_converts_empty_dict_to_querystring(self):
        expected = ""
        actual = utils.dict_to_querystring({})
        assert actual == expected
