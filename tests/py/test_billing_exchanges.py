from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

import balanced
import mock
import pytest

from aspen.utils import typecheck
from gittip.billing.exchanges import (
    _prep_hit,
    charge,
    charge_on_balanced,
    record_exchange,
    skim_credit,
)
from gittip.exceptions import NegativeBalance, NoBalancedCustomerHref
from gittip.models.participant import Participant
from gittip.testing import Harness
from gittip.testing.balanced import BalancedHarness


class TestCharge(BalancedHarness):

    def test_charge_without_cc_details_raises_NoBalancedCustomerHref(self):
        alice = self.make_participant('alice')
        with self.assertRaises(NoBalancedCustomerHref):
            charge(self.db, alice, D('1.00'))

    @mock.patch('gittip.billing.exchanges.charge_on_balanced')
    def test_charge_failure_returns_error(self, cob):
        cob.return_value = (D('10.00'), D('0.68'), 'FAILED')
        actual = charge(self.db, self.janet, D('1.00'))
        assert actual == 'FAILED'

    @mock.patch('gittip.billing.exchanges.charge_on_balanced')
    def test_charge_success_returns_empty_string(self, charge_on_balanced):
        charge_on_balanced.return_value = (D('10.00'), D('0.68'), "")
        actual = charge(self.db, self.janet, D('1.00'))
        assert actual == ''

    @mock.patch('gittip.billing.exchanges.charge_on_balanced')
    def test_charge_success_updates_participant(self, cob):
        cob.return_value = (D('10.00'), D('0.68'), "")
        charge(self.db, self.janet, D('1.00'))

        janet = Participant.from_username('janet')
        expected = {'balance': D('9.32'), 'last_bill_result': ''}
        actual = {'balance': janet.balance,
                  'last_bill_result': janet.last_bill_result}
        assert actual == expected


class TestChargeOnBalanced(BalancedHarness):

    def test_charge_on_balanced(self):
        actual = charge_on_balanced( 'janet'
                                   , self.janet_href
                                   , D('10.00') # $10.00 USD
                                    )
        assert actual == (D('10.61'), D('0.61'), '')

    def test_charge_on_balanced_small_amount(self):
        actual = charge_on_balanced( 'janet'
                                   , self.janet_href
                                   , D('0.06')  # $0.06 USD
                                    )
        assert actual == (D('10.00'), D('0.59'), '')

    def test_charge_on_balanced_failure(self):
        customer_with_bad_card = self.make_balanced_customer()
        card = balanced.Card(
            number='4444444444444448',
            expiration_year=2020,
            expiration_month=12
        ).save()
        card.associate_to_customer(customer_with_bad_card)

        actual = charge_on_balanced( 'whatever username'
                                   , customer_with_bad_card
                                   , D('10.00')
                                    )
        assert actual == (D('10.61'), D('0.61'), '402 Client Error: PAYMENT REQUIRED')

    def test_charge_on_balanced_handles_MultipleFoundError(self):
        customer_href = self.make_balanced_customer()
        card = balanced.Card(
            number='4242424242424242',
            expiration_year=2020,
            expiration_month=12
        ).save()
        card.associate_to_customer(customer_href)

        card = balanced.Card(
            number='4242424242424242',
            expiration_year=2030,
            expiration_month=12
        ).save()
        card.associate_to_customer(customer_href)

        actual = charge_on_balanced( 'whatever username'
                                   , customer_href
                                   , D('10.00')
                                    )
        assert actual == (D('10.61'), D('0.61'), 'MultipleResultsFound()')

    def test_charge_on_balanced_handles_NotFoundError(self):
        customer_with_no_card = self.make_balanced_customer()
        actual = charge_on_balanced( 'whatever username'
                                   , customer_with_no_card
                                   , D('10.00')
                                    )
        assert actual == (D('10.61'), D('0.61'), 'NoResultFound()')


class TestFees(Harness):

    def prep(self, amount):
        """Given a dollar amount as a string, return a 3-tuple.

        The return tuple is like the one returned from _prep_hit, but with the
        second value, a log message, removed.

        """
        typecheck(amount, unicode)
        out = list(_prep_hit(D(amount)))
        out = [out[0]] + out[2:]
        return tuple(out)

    def test_prep_hit_basically_works(self):
        actual = _prep_hit(D('20.00'))
        expected = (2091,
                    u'Charging %s 2091 cents ($20.00 + $0.91 fee = $20.91) on %s ' u'... ',
                    D('20.91'), D('0.91'))
        assert actual == expected

    def test_prep_hit_full_in_rounded_case(self):
        actual = _prep_hit(D('5.00'))
        expected = (1000,
                    u'Charging %s 1000 cents ($9.41 [rounded up from $5.00] + ' u'$0.59 fee = $10.00) on %s ... ',
                    D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_ten_dollars(self):
        actual = self.prep(u'10.00')
        expected = (1061, D('10.61'), D('0.61'))
        assert actual == expected

    def test_prep_hit_at_forty_cents(self):
        actual = self.prep(u'0.40')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_fifty_cents(self):
        actual = self.prep(u'0.50')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_sixty_cents(self):
        actual = self.prep(u'0.60')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_eighty_cents(self):
        actual = self.prep(u'0.80')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_nine_fifteen(self):
        actual = self.prep(u'9.15')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_nine_forty(self):
        actual = self.prep(u'9.40')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_nine_forty_one(self):
        actual = self.prep(u'9.41')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_nine_forty_two(self):
        actual = self.prep(u'9.42')
        expected = (1002, D('10.02'), D('0.60'))
        assert actual == expected

    def test_skim_credit(self):
        actual = skim_credit(D('10.00'))
        assert actual == (D('10.00'), D('0.00'))


class TestRecordExchange(Harness):

    def test_record_exchange_updates_balance(self):
        alice = self.make_participant('alice')
        record_exchange( self.db
                       , 'bill'
                       , amount=D("0.59")
                       , fee=D("0.41")
                       , error=""
                       , participant=alice
                        )
        alice = Participant.from_username('alice')
        assert alice.balance == D("0.59")

    def test_record_exchange_fails_if_negative_balance(self):
        alice = self.make_participant('alice')
        pytest.raises( NegativeBalance
                     , record_exchange
                     , self.db
                     , 'ach'
                     , amount=D("-10.00")
                     , fee=D("0.41")
                     , error=""
                     , participant=alice
                      )

    def test_record_exchange_doesnt_update_balance_if_error(self):
        alice = self.make_participant('alice')
        record_exchange( self.db
                       , 'bill'
                       , amount=D("1.00")
                       , fee=D("0.41")
                       , error="SOME ERROR"
                       , participant=alice
                        )
        alice = Participant.from_username('alice')
        assert alice.balance == D("0.00")
