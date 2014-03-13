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

    def test_linkify_linkifies_url_with_www(self):
        expected = '<a href="http://www.example.com" target="_blank">http://www.example.com</a>'
        actual = utils.linkify('http://www.example.com')
        assert actual == expected

    def test_linkify_linkifies_url_without_www(self):
        expected = '<a href="http://example.com" target="_blank">http://example.com</a>'
        actual = utils.linkify('http://example.com')
        assert actual == expected

    def test_linkify_linkifies_url_with_uppercase_letters(self):
        expected = '<a href="Http://Www.Example.Com" target="_blank">Http://Www.Example.Com</a>'
        actual = utils.linkify('Http://Www.Example.Com')
        assert actual == expected

    def test_linkify_works_without_protocol(self):
        expected = '<a href="http://www.example.com" target="_blank">www.example.com</a>'
        actual = utils.linkify('www.example.com')
        assert actual == expected
