from __future__ import division, print_function, unicode_literals

from mock import patch

from liberapay.billing.transactions import swap_currencies, Transfer
from liberapay.exceptions import NegativeBalance, TransferError
from liberapay.testing import EUR, USD, Harness, Foobar
from liberapay.testing.mangopay import FakeTransfersHarness, MangopayHarness, fake_transfer
from liberapay.utils.currencies import MoneyBasket


class TestCurrencies(Harness):

    def test_convert(self):
        original = EUR('1.00')
        expected = USD('1.20')
        actual = self.db.one("SELECT convert(%s, %s)", (original, expected.currency))
        assert expected == actual
        actual = original.convert(expected.currency)
        assert expected == actual

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
