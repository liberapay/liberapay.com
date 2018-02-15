from __future__ import division, print_function, unicode_literals

from liberapay.testing import EUR, USD, Harness


class TestCurrencies(Harness):

    def test_convert(self):
        original = EUR('1.00')
        expected = USD('1.20')
        actual = self.db.one("SELECT convert(%s, %s)", (original, expected.currency))
        assert expected == actual
        actual = original.convert(expected.currency)
        assert expected == actual
