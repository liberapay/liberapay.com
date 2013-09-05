from __future__ import print_function, unicode_literals

from nose.tools import assert_equals

from gittip.testing import Harness
from gittip.testing.client import TestClient
from gittip.models.participant import Participant


class TestIsSuspicious(Harness):
    def setUp(self):
        super(Harness, self).setUp()
        self.make_participant('bar', is_admin=True)

    def toggle_is_suspicious(self):
        client = TestClient()
        client.get('/foo/toggle-is-suspicious.json', user='bar')

    def test_that_is_suspicious_defaults_to_None(self):
        foo = self.make_participant('foo')
        actual = foo.is_suspicious
        assert_equals(actual, None)

    def test_toggling_NULL_gives_true(self):
        self.make_participant('foo')
        self.toggle_is_suspicious()
        actual = Participant.from_username('foo').is_suspicious
        assert_equals(actual, True)

    def test_toggling_true_gives_false(self):
        self.make_participant('foo', is_suspicious=True)
        self.toggle_is_suspicious()
        actual = Participant.from_username('foo').is_suspicious
        assert_equals(actual, False)

    def test_toggling_false_gives_true(self):
        self.make_participant('foo', is_suspicious=False)
        self.toggle_is_suspicious()
        actual = Participant.from_username('foo').is_suspicious
        assert_equals(actual, True)
