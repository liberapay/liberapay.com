from decimal import Decimal as D
from unittest.mock import patch

import pytest

from liberapay.billing.transactions import swap_currencies, Transfer
from liberapay.constants import CURRENCIES, DONATION_LIMITS, STANDARD_TIPS
from liberapay.exceptions import NegativeBalance, TransferError
from liberapay.i18n.currencies import Money, MoneyBasket
from liberapay.payin.stripe import int_to_Money, Money_to_int
from liberapay.testing import EUR, JPY, USD, Harness, Foobar
from liberapay.testing.mangopay import FakeTransfersHarness, MangopayHarness, fake_transfer


class TestCurrencies(Harness):

    def test_convert(self):
        original = EUR('1.00')
        expected = USD('1.20')
        actual = self.db.one("SELECT convert(%s, %s)", (original, expected.currency))
        assert expected == actual
        actual = original.convert(expected.currency)
        assert expected == actual

    def test_convert_non_euro(self):
        original = Money('1.00', 'CHF')
        expected = Money('0.82', 'GBP')
        actual = self.db.one("SELECT convert(%s, %s)", (original, expected.currency))
        assert expected == actual
        actual = original.convert(expected.currency)
        assert expected == actual

        original = Money('1.20', 'USD')
        expected = Money('125', 'JPY')
        actual = self.db.one("SELECT convert(%s, %s)", (original, expected.currency))
        assert expected == actual
        actual = original.convert(expected.currency)
        assert expected == actual

    def test_minimums(self):
        assert Money.MINIMUMS['EUR'].amount == D('0.01')
        assert Money.MINIMUMS['USD'].amount == D('0.01')
        assert Money.MINIMUMS['KRW'].amount == D('1')
        assert Money.MINIMUMS['JPY'].amount == D('1')

    def test_rounding(self):
        assert Money('0.001', 'EUR').round() == Money('0.00', 'EUR')
        assert Money('0.009', 'EUR').round_down() == Money('0.00', 'EUR')
        assert Money('0.002', 'EUR').round_up() == Money('0.01', 'EUR')
        assert Money('0.1', 'JPY').round() == Money('0', 'JPY')
        assert Money('0.9', 'JPY').round_down() == Money('0', 'JPY')
        assert Money('0.2', 'JPY').round_up() == Money('1', 'JPY')

    def test_MoneyBasket_currencies_present(self):
        b = MoneyBasket()
        assert b.currencies_present == []
        b = MoneyBasket(USD=1)
        assert b.currencies_present == ['USD']
        b = MoneyBasket(EUR=0, USD=1)
        assert b.currencies_present == ['USD']
        b = MoneyBasket(EUR=-1, USD=1)
        assert b.currencies_present == ['USD']
        b = MoneyBasket(EUR=10, USD=1)
        assert b.currencies_present == ['EUR', 'USD']

    def test_MoneyBasket_comparisons(self):
        b = MoneyBasket()
        assert b == 0
        b = MoneyBasket(USD=1)
        assert b > 0
        b = MoneyBasket()
        b2 = MoneyBasket(EUR=1, USD=1)
        assert not (b >= b2)

    def test_donation_limits(self):
        for currency in CURRENCIES:
            currency_minimum = Money.MINIMUMS[currency]
            currency_exponent = currency_minimum.amount.as_tuple()[2]
            limits = DONATION_LIMITS[currency]
            for period, (min_limit, max_limit) in limits.items():
                print(period, min_limit, max_limit)
                assert min_limit >= currency_minimum
                assert max_limit > min_limit
                assert min_limit.amount.as_tuple()[2] >= currency_exponent
                assert max_limit.amount.as_tuple()[2] >= currency_exponent
                if period == 'weekly':
                    assert len(min_limit.amount.normalize().as_tuple().digits) <= 2

    def test_standard_tips(self):
        for currency in CURRENCIES:
            minimum = Money.MINIMUMS[currency]
            min_exponent = minimum.amount.as_tuple()[2]
            standard_tips = STANDARD_TIPS[currency]
            for st in standard_tips:
                print(st)
                assert st.weekly >= minimum
                assert st.weekly.amount.as_tuple()[2] >= min_exponent
                assert st.monthly.amount.as_tuple()[2] >= min_exponent
                assert st.yearly.amount.as_tuple()[2] >= min_exponent
                assert len(st.weekly.amount.normalize().as_tuple().digits) <= 2


class TestCurrenciesInDB(Harness):

    def test_parsing_currency_amount(self):
        expected = EUR('1.23')
        actual = self.db.one("SELECT %s", (expected,))
        assert expected == actual

    def test_parsing_currency_basket(self):
        # Empty basket
        expected = MoneyBasket()
        actual = self.db.one("SELECT empty_currency_basket()")
        assert expected == actual
        # Non-empty basket
        expected = MoneyBasket(USD=D('0.88'))
        actual = self.db.one("SELECT make_currency_basket(('0.88','USD'))")
        assert expected == actual
        # Non-empty legacy basket
        expected = MoneyBasket(EUR=D('3.21'))
        actual = self.db.one("SELECT ('3.21','0.00',NULL)::currency_basket")
        assert expected == actual

    def test_add_to_basket(self):
        # Add to empty basket
        expected = MoneyBasket(GBP=D('1.05'))
        actual = self.db.one("SELECT empty_currency_basket() + %s AS x", (expected['GBP'],))
        assert expected == actual
        # Add to non-empty sum
        expected = MoneyBasket(EUR=D('0.33'), USD=D('0.77'))
        actual = self.db.one("SELECT basket_sum(x) FROM unnest(%s) x", (list(expected),))
        assert expected == actual

    def test_merge_two_baskets(self):
        # Merge empty basket left
        expected = MoneyBasket(GBP=D('1.05'))
        actual = self.db.one("SELECT empty_currency_basket() + %s AS x", (expected,))
        assert expected == actual
        # Merge empty basket right
        expected = MoneyBasket(GBP=D('1.06'))
        actual = self.db.one("SELECT %s + empty_currency_basket() AS x", (expected,))
        assert expected == actual
        # Merge non-empty baskets
        b1 = MoneyBasket(JPY=D('101'))
        b2 = MoneyBasket(EUR=D('1.02'), JPY=D('101'))
        expected = b1 + b2
        actual = self.db.one("SELECT %s + %s AS x", (b1, b2))
        assert expected == actual
        # Merge empty legacy basket
        b1 = MoneyBasket(EUR=D('1.01'))
        b2 = MoneyBasket(EUR=D('1.02'), JPY=D('45'))
        expected = b1 + b2
        actual = self.db.one("""
            SELECT (%s,'0.00',NULL)::currency_basket + %s AS x
        """, (b1.amounts['EUR'], b2))
        assert expected == actual

    def test_basket_sum(self):
        # Empty sum
        expected = MoneyBasket()
        actual = self.db.one("SELECT basket_sum(x) FROM unnest(NULL::currency_amount[]) x")
        assert expected == actual
        actual = self.db.one("SELECT basket_sum(x) FROM unnest(ARRAY[NULL]::currency_amount[]) x")
        assert expected == actual
        # Non-empty sum
        expected = MoneyBasket(EUR=D('0.33'), USD=D('0.77'))
        actual = self.db.one("SELECT basket_sum(x) FROM unnest(%s) x", (list(expected) + [None],))
        assert expected == actual

    def test_sums(self):
        # Empty sum
        actual = self.db.one("SELECT sum(x) FROM unnest(NULL::currency_amount[]) x")
        assert actual is None
        actual = self.db.one("SELECT sum(x) FROM unnest(ARRAY[NULL]::currency_amount[]) x")
        assert actual is None
        # Empty fuzzy sum
        actual = self.db.one("SELECT sum(x, 'EUR') FROM unnest(NULL::currency_amount[]) x")
        assert actual is None
        actual = self.db.one("SELECT sum(x, 'EUR') FROM unnest(ARRAY[NULL]::currency_amount[]) x")
        assert actual is None
        # Single-currency sum
        amounts = [JPY('133'), JPY('977')]
        expected = sum(amounts)
        actual = self.db.one("SELECT sum(x, 'JPY') FROM unnest(%s) x", (amounts + [None],))
        assert expected == actual
        # Fuzzy sum
        amounts = [EUR('0.50'), USD('1.20')]
        expected = MoneyBasket(*amounts).fuzzy_sum('EUR')
        actual = self.db.one("SELECT sum(x, 'EUR') FROM unnest(%s) x", (amounts + [None],))
        assert expected == actual, (expected.__dict__, actual.__dict__)

    @pytest.mark.xfail
    def test_sorting(self):
        amounts = [JPY('130'), EUR('99.58'), Money('79', 'KRW'), USD('35.52')]
        expected = sorted(amounts, key=lambda m: -m.convert('EUR').amount)
        actual = self.db.all("SELECT x FROM unnest(%s) x ORDER BY x DESC", (amounts,))
        assert expected == actual


class TestCurrenciesSimplate(Harness):

    def test_edit_currencies(self):
        alice = self.make_participant('alice', main_currency='EUR', accepted_currencies='EUR')
        assert alice.main_currency == 'EUR'
        assert alice.accepted_currencies == 'EUR'
        assert alice.accepted_currencies_set == set(['EUR'])

        r = self.client.PxST('/alice/edit/currencies', {
            'accepted_currencies': '*',
            'main_currency': 'USD',
        }, auth_as=alice)
        assert r.code == 302, r.text
        alice = alice.refetch()
        assert alice.main_currency == 'USD'
        assert alice.accepted_currencies is None
        assert alice.accepted_currencies_set is CURRENCIES

        r = self.client.PxST('/alice/edit/currencies', {
            'accepted_currencies:JPY': 'yes',
            'main_currency': 'JPY',
        }, auth_as=alice)
        assert r.code == 302, r.text
        alice = alice.refetch()
        assert alice.main_currency == 'JPY'
        assert alice.accepted_currencies == 'JPY'
        assert alice.accepted_currencies_set == set(['JPY'])

        r = self.client.PxST('/alice/edit/currencies', {
            'accepted_currencies:JPY': 'yes',
            'main_currency': 'KRW',
        }, auth_as=alice)
        assert r.code == 400, r.text
        alice = alice.refetch()
        assert alice.main_currency == 'JPY'
        assert alice.accepted_currencies == 'JPY'
        assert alice.accepted_currencies_set == set(['JPY'])


class TestCurrencySwap(FakeTransfersHarness, MangopayHarness):

    @patch('mangopay.resources.TransferRefund.save', autospec=True)
    def test_swap_currencies(self, TR_save):
        TR_save.side_effect = fake_transfer

        self.make_exchange('mango-cc', EUR('10.00'), 0, self.janet)
        self.make_exchange('mango-cc', USD('7.00'), 0, self.homer)
        start_balances = {
            'janet': EUR('10.00'),
            'homer': USD('7.00'),
            'david': MoneyBasket(),
        }
        balances = self.get_balances()
        assert balances == start_balances

        # Test failure when there isn't enough money in the 1st wallet
        with self.assertRaises(AssertionError):
            swap_currencies(self.db, self.janet, self.homer, EUR('100.00'), USD('120.00'))
        balances = self.get_balances()
        assert balances == start_balances

        # Test failure when there isn't enough money in the 2nd wallet
        with self.assertRaises(AssertionError):
            swap_currencies(self.db, self.janet, self.homer, EUR('10.00'), USD('12.00'))
        balances = self.get_balances()
        assert balances == start_balances

        # Test failure of the 1st `prepare_transfer()` call
        with patch('liberapay.billing.transactions.lock_bundles') as lock_bundles:
            lock_bundles.side_effect = NegativeBalance
            with self.assertRaises(NegativeBalance):
                swap_currencies(self.db, self.janet, self.homer, EUR('3.00'), USD('3.00'))
        balances = self.get_balances()
        assert balances == start_balances

        # Test failure of the 2nd `prepare_transfer()` call
        cash_bundle = self.db.one("SELECT * FROM cash_bundles WHERE owner = %s", (self.homer.id,))
        self.db.run("UPDATE cash_bundles SET amount = %s WHERE id = %s",
                    (USD('0.01'), cash_bundle.id))
        with self.assertRaises(NegativeBalance):
            swap_currencies(self.db, self.janet, self.homer, EUR('5.00'), USD('6.99'))
        self.db.run("UPDATE cash_bundles SET amount = %s WHERE id = %s",
                    (cash_bundle.amount, cash_bundle.id))
        balances = self.get_balances()
        assert balances == start_balances

        # Test failure of the 1st `initiate_transfer()` call
        self.transfer_mock.side_effect = Foobar
        with self.assertRaises(TransferError):
            swap_currencies(self.db, self.janet, self.homer, EUR('4.25'), USD('5.55'))
        balances = self.get_balances()
        assert balances == start_balances

        # Test failure of the 2nd `initiate_transfer()` call
        def fail_on_second(tr):
            if getattr(fail_on_second, 'called', False):
                raise Foobar
            fail_on_second.called = True
            fake_transfer(tr)
        self.transfer_mock.side_effect = fail_on_second
        self.db.run("ALTER SEQUENCE transfers_id_seq RESTART WITH 1")
        with patch('mangopay.resources.Transfer.get') as T_get:
            T_get.return_value = Transfer(Id=-1, AuthorId=self.janet_id, Tag='1')
            with self.assertRaises(TransferError):
                swap_currencies(self.db, self.janet, self.homer, EUR('0.01'), USD('0.01'))
        balances = self.get_balances()
        assert balances == start_balances

        # Test success
        self.transfer_mock.side_effect = fake_transfer
        swap_currencies(self.db, self.janet, self.homer, EUR('5.00'), USD('6.00'))
        balances = self.get_balances()
        assert balances == {
            'janet': MoneyBasket(EUR('5.00'), USD('6.00')),
            'homer': MoneyBasket(EUR('5.00'), USD('1.00')),
            'david': MoneyBasket(),
        }


class TestCurrenciesWithStripe(Harness):

    def test_Money_to_int(self):
        expected = 101
        actual = Money_to_int(EUR('1.01'))
        assert expected == actual
        expected = 1
        actual = Money_to_int(JPY('1'))
        assert expected == actual

    def test_int_to_Money(self):
        expected = USD('1.02')
        actual = int_to_Money(102, 'USD')
        assert expected == actual
        expected = JPY('1')
        actual = int_to_Money(1, 'JPY')
        assert expected == actual
