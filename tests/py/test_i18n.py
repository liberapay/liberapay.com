from liberapay.exceptions import AmbiguousNumber, InvalidNumber
from liberapay.i18n.base import CURRENCIES_MAP, DEFAULT_CURRENCY, LOCALE_EN, Money
from liberapay.testing import Harness


class Tests(Harness):

    def test_currencies_map(self):
        assert CURRENCIES_MAP['BR'] == 'BRL'
        assert CURRENCIES_MAP['CH'] == 'CHF'
        assert CURRENCIES_MAP['DE'] == 'EUR'
        assert CURRENCIES_MAP['JP'] == 'JPY'
        assert CURRENCIES_MAP['US'] == 'USD'
        assert CURRENCIES_MAP['ZA'] == 'ZAR'

    def test_request_country(self):
        request = self.client.GET('/', want='request')
        assert request.country is None
        request = self.client.GET('/', HTTP_CF_IPCOUNTRY='US', want='request')
        assert request.country == 'US'

    def test_state_currency(self):
        state = self.client.GET('/', want='state')
        assert state['currency'] is DEFAULT_CURRENCY
        state = self.client.GET('/', HTTP_CF_IPCOUNTRY='CH', want='state')
        assert state['currency'] == 'CHF'
        state = self.client.GET('/', HTTP_CF_IPCOUNTRY='US', want='state')
        assert state['currency'] == 'USD'

    def test_default_donation_currency(self):
        alice = self.make_participant('alice', main_currency='KRW', accepted_currencies=None)
        self.add_payment_account(alice, 'stripe', 'KR')
        self.add_payment_account(alice, 'paypal', 'KR')
        r = self.client.GET('/alice/donate')
        assert '<input type="hidden" name="currency" value="KRW" />' in r.text, r.text

    def test_format_money_without_trailing_zeroes(self):
        result = LOCALE_EN.format_money(Money(16, 'USD'), trailing_zeroes=False)
        assert result == '$16'
        result = LOCALE_EN.format_money(Money(5555, 'KRW'), trailing_zeroes=False)
        assert result == '₩5,555'

    def test_format_money_defaults_to_trailing_zeroes(self):
        result = LOCALE_EN.format_money(Money(16, 'USD'))
        assert result == '$16.00'
        result = LOCALE_EN.format_money(Money(5555, 'KRW'))
        assert result == '₩5,555'

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
