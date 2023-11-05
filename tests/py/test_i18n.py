from liberapay.constants import CURRENCIES, PAYPAL_CURRENCIES
from liberapay.exceptions import AmbiguousNumber, InvalidNumber
from liberapay.i18n.base import CURRENCIES_MAP, DEFAULT_CURRENCY, LOCALE_EN, Money
from liberapay.security.authentication import ANON
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
        assert request.source_country is None
        request = self.client.GET('/', HTTP_CF_IPCOUNTRY='US', want='request')
        assert request.source_country == 'US'

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

    def test_parse_money_amount_tolerates_spaces_and_matching_currency_symbols(self):
        assert LOCALE_EN.parse_money_amount("$1", 'USD')
        assert LOCALE_EN.parse_money_amount(" € 2,000.22 ", 'EUR')
        assert LOCALE_EN.parse_money_amount("3€", 'EUR')
        locale_fr = self.website.locales['fr-fr']
        assert locale_fr.parse_money_amount("  4 000,99  €  ", 'EUR')
        with self.assertRaises(InvalidNumber):
            LOCALE_EN.parse_money_amount("$100", 'EUR')

    def test_chinese_visitor_gets_chinese_locale(self):
        state = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=b'zh', want='state')
        assert state['locale'] is self.website.locales['zh-hans']
        state = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=b'zh-CN', want='state')
        assert state['locale'] is self.website.locales['zh-hans-cn']
        state = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=b'zh-TW', want='state')
        assert state['locale'] is self.website.locales['zh-hant-tw']
        state = self.client.GET(
            '/', HTTP_ACCEPT_LANGUAGE=b'zh', HTTP_CF_IPCOUNTRY='TW', want='state'
        )
        assert state['locale'] is self.website.locales['zh-hant-tw']
        state = self.client.GET(
            '/', HTTP_ACCEPT_LANGUAGE=b'zh-Hant-TW', HTTP_CF_IPCOUNTRY='CN', want='state'
        )
        assert state['locale'] is self.website.locales['zh-hant-tw']

    def test_american_english(self):
        state = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=b'en-us', want='state')
        locale = state['locale']
        assert locale is self.website.locales['en-us']
        assert locale.tag == 'en-us'
        assert locale.format_money(Money('5200.00', 'USD')) == '$5,200.00'
        assert locale.parse_money_amount('5,200.00', 'USD') == Money('5200.00', 'USD')
        assert not state.get('partial_translation')

    def test_swiss_german(self):
        state = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=b'de-ch', want='state')
        locale = state['locale']
        assert locale is self.website.locales['de-ch']
        assert locale.tag == 'de-ch'
        assert locale.format_money(Money('5200.00', 'EUR')) == 'EUR 5’200.00'
        assert locale.parse_money_amount('5’200.00', 'EUR') == Money('5200.00', 'EUR')

    def test_get_currencies_for(self):
        # Unidentified donor with a Swiss IP address, giving to a creator in France.
        alice = self.make_participant(
            'alice', main_currency='EUR', accepted_currencies='EUR,USD',
            email='alice@liberapay.com',
        )
        self.add_payment_account(alice, 'stripe', 'FR', default_currency='EUR')
        self.add_payment_account(alice, 'paypal', 'FR', default_currency='EUR')
        alice = alice.refetch()
        assert alice.payment_providers == 3
        tip = ANON.get_tip_to(alice, currency='CHF')
        recommended_currency, accepted_currencies = ANON.get_currencies_for(alice, tip)
        assert recommended_currency == 'EUR'
        assert accepted_currencies == {'EUR', 'USD'}

        # Unidentified donor with an Indonesian IP address, giving to a creator in Iceland.
        # The PayPal API we're using doesn't support the Icelandic Króna, so we fall back to USD.
        bob = self.make_participant(
            'bob', main_currency='ISK', accepted_currencies='ISK',
            email='bob@liberapay.com',
        )
        self.add_payment_account(bob, 'paypal', 'IS', default_currency='ISK')
        bob = bob.refetch()
        assert bob.payment_providers == 2
        tip = ANON.get_tip_to(bob, currency='IDR')
        recommended_currency, accepted_currencies = ANON.get_currencies_for(bob, tip)
        assert recommended_currency == 'USD'
        assert accepted_currencies == PAYPAL_CURRENCIES

        # Logged-in Russian donor with a Swedish IP address, giving to a creator in France.
        zarina = self.make_participant('zarina', main_currency='RUB')
        tip = zarina.get_tip_to(alice, currency='SEK')
        recommended_currency, accepted_currencies = zarina.get_currencies_for(alice, tip)
        assert recommended_currency == 'EUR'
        assert accepted_currencies == {'EUR', 'USD'}

        # Logged-in Russian donor with a German IP address,
        # giving to a creator in Mexico who accepts all currencies.
        carl = self.make_participant('carl', main_currency='MXN', accepted_currencies=None)
        tip = zarina.get_tip_to(carl, currency='EUR')
        recommended_currency, accepted_currencies = zarina.get_currencies_for(carl, tip)
        assert recommended_currency == 'RUB'
        assert accepted_currencies == CURRENCIES
