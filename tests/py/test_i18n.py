# coding: utf8

from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.testing import Harness
from liberapay.utils.i18n import LOCALE_EN, Money


class Tests(Harness):

    def test_format_currency_without_trailing_zeroes(self):
        expected = '$16'
        actual = LOCALE_EN.format_money(Money(16, 'USD'), trailing_zeroes=False)
        assert actual == expected

    def test_format_currency_defaults_to_trailing_zeroes(self):
        expected = '$16.00'
        actual = LOCALE_EN.format_money(Money(16, 'USD'))
        assert actual == expected

    def test_locales_share_message_keys(self):
        msgkey1 = self.website.locales['de'].catalog['Save'].id
        msgkey2 = self.website.locales['fr'].catalog['Save'].id
        assert id(msgkey1) == id(msgkey2)
