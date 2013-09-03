from __future__ import division, print_function, unicode_literals

from gittip import utils
from gittip.testing import Harness, load_request
from gittip.elsewhere.twitter import TwitterAccount


class Tests(Harness):

    def test_get_participant_gets_participant(self):
        expected, ignored = TwitterAccount("alice", {}).opt_in("alice")
        request = load_request('/alice/')

        actual = utils.get_participant(request, restrict=False)
        assert actual == expected, actual

    def test_get_participant_canonicalizes(self):
        expected, ignored = TwitterAccount("alice", {}).opt_in("alice")
        request = load_request('/Alice/')

        actual = utils.get_participant(request, restrict=False)
        assert actual == expected, actual
