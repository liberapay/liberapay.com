from __future__ import absolute_import, division, print_function, unicode_literals

from aspen import Response
from gittip import utils
from gittip.testing import Harness, load_request


class Tests(Harness):

    def test_get_participant_gets_participant(self):
        elsewhere = self.make_elsewhere("twitter", "alice")
        expected = elsewhere.opt_in("alice")[0].participant

        request = load_request(b'/alice/')
        actual = utils.get_participant(request, restrict=False)
        assert actual == expected

    def test_get_participant_canonicalizes(self):
        self.make_elsewhere("twitter", "alice").opt_in("alice")

        request = load_request(b'/Alice/')
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
