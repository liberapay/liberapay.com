# coding: utf8

from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.exceptions import AmbiguousNumber, InvalidNumber
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

    def test_parse_money_amount_rejects_overly_precise_numbers(self):
        with self.assertRaises(InvalidNumber):
            LOCALE_EN.parse_money_amount("100.00001", 'EUR')

    def test_parse_money_amount_rejects_irregular_numbers(self):
        with self.assertRaises(AmbiguousNumber):
            LOCALE_EN.parse_money_amount(",100,100", 'USD')

    def test_parse_money_amount_rejects_ambiguous_numbers(self):
        with self.assertRaises(AmbiguousNumber):
            LOCALE_EN.parse_money_amount("10,00", 'EUR')

    def test_chinese_visitor_gets_chinese_locale(self):
        state = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=b'zh', want='state')
        assert state['locale'] == self.website.locales['zh']
        state = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=b'zh_Hans', want='state')
        assert state['locale'] == self.website.locales['zh']
        state = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=b'zh-CN', want='state')
        assert state['locale'] == self.website.locales['zh']
