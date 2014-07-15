from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

import balanced
import mock
import pytest

from aspen.utils import typecheck
from gittip.billing.exchanges import (
    _prep_hit,
    ach_credit,
    cancel_card_hold,
    capture_card_hold,
    create_card_hold,
    record_exchange,
    skim_credit,
)
from gittip.exceptions import NegativeBalance, NoBalancedCustomerHref, NotWhitelisted
from gittip.models.participant import Participant
from gittip.testing import Harness, raise_foobar
from gittip.testing.balanced import BalancedHarness


class TestCredits(BalancedHarness):

    def test_ach_credit_withhold(self):
        bob = self.make_participant('bob', last_ach_result="failure", balance=20,
                                    balanced_customer_href=self.homer_href,
                                    is_suspicious=False)
        withhold = D('1.00')
        error = ach_credit(self.db, bob, withhold)
        assert error == ''
        bob2 = Participant.from_id(bob.id)
        assert bob.balance == bob2.balance == 1

    def test_ach_credit_amount_under_minimum(self):
        bob = self.make_participant('bob', last_ach_result="failure", balance=8,
                                    balanced_customer_href=self.homer_href,
                                    is_suspicious=False)
        r = ach_credit(self.db, bob, 0)
        assert r is None

    @mock.patch('balanced.Customer')
    def test_ach_credit_failure(self, Customer):
        Customer.fetch = raise_foobar
        bob = self.make_participant('bob', last_ach_result="failure", balance=20,
                                    balanced_customer_href=self.homer_href,
                                    is_suspicious=False)

        error = ach_credit(self.db, bob, D('1.00'))
        bob2 = Participant.from_id(bob.id)
        assert bob.last_ach_result == bob2.last_ach_result == error == "Foobar()"
        assert bob.balance == bob2.balance == 20


class TestCardHolds(BalancedHarness):

    def test_create_card_hold_without_cc_details_raises_NoBalancedCustomerHref(self):
        alice = self.make_participant('alice')
        with self.assertRaises(NoBalancedCustomerHref):
            create_card_hold(self.db, alice, D('1.00'))

    def test_create_card_hold_for_suspicious_raises_NotWhitelisted(self):
        bob = self.make_participant('bob', is_suspicious=True,
                                    balanced_customer_href='fake_href')
        with self.assertRaises(NotWhitelisted):
            create_card_hold(self.db, bob, D('1.00'))

    @mock.patch('balanced.Customer')
    def test_create_card_hold_failure(self, Customer):
        Customer.fetch = raise_foobar
        hold, error = create_card_hold(self.db, self.janet, D('1.00'))
        assert hold is None
        assert error == "Foobar()"

    def test_create_card_hold_success(self):
        hold, error = create_card_hold(self.db, self.janet, D('1.00'))
        janet = Participant.from_id(self.janet.id)
        assert isinstance(hold, balanced.CardHold)
        assert hold.failure_reason is None
        assert hold.amount == 1000
        assert hold.meta['state'] == 'new'
        assert error == ''
        assert self.janet.balance == janet.balance == 0

        # Clean up
        cancel_card_hold(hold)

    def test_capture_card_hold_full_amount(self):
        hold, error = create_card_hold(self.db, self.janet, D('20.00'))
        assert error == ''  # sanity check
        assert hold.meta['state'] == 'new'

        capture_card_hold(self.db, self.janet, D('20.00'), hold)
        janet = Participant.from_id(self.janet.id)
        assert self.janet.balance == janet.balance == D('20.00')
        assert self.janet.last_bill_result == janet.last_bill_result == ''
        assert hold.meta['state'] == 'captured'

    def test_capture_card_hold_partial_amount(self):
        hold, error = create_card_hold(self.db, self.janet, D('20.00'))
        assert error == ''  # sanity check

        capture_card_hold(self.db, self.janet, D('15.00'), hold)
        janet = Participant.from_id(self.janet.id)
        assert self.janet.balance == janet.balance == D('15.00')
        assert self.janet.last_bill_result == janet.last_bill_result == ''

    def test_capture_card_hold_too_high_amount(self):
        hold, error = create_card_hold(self.db, self.janet, D('20.00'))
        assert error == ''  # sanity check

        with self.assertRaises(balanced.exc.HTTPError):
            capture_card_hold(self.db, self.janet, D('20.01'), hold)

        janet = Participant.from_id(self.janet.id)
        assert self.janet.balance == janet.balance == 0

        # Clean up
        cancel_card_hold(hold)

    def test_capture_card_hold_amount_under_minimum(self):
        hold, error = create_card_hold(self.db, self.janet, D('20.00'))
        assert error == ''  # sanity check

        capture_card_hold(self.db, self.janet, D('0.01'), hold)
        janet = Participant.from_id(self.janet.id)
        assert self.janet.balance == janet.balance == D('9.41')
        assert self.janet.last_bill_result == janet.last_bill_result == ''

    def test_create_card_hold_bad_card(self):
        customer_href = self.make_balanced_customer()
        card = balanced.Card(
            number='4444444444444448',
            expiration_year=2020,
            expiration_month=12
        ).save()
        card.associate_to_customer(customer_href)

        bob = self.make_participant('bob', balanced_customer_href=customer_href,
                                    is_suspicious=False)
        hold, error = create_card_hold(self.db, bob, D('10.00'))
        assert error == '402 Client Error: PAYMENT REQUIRED'

    def test_create_card_hold_multiple_cards(self):
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

        bob = self.make_participant('bob', balanced_customer_href=customer_href,
                                    is_suspicious=False)
        hold, error = create_card_hold(self.db, bob, D('10.00'))
        assert error == 'MultipleResultsFound()'

    def test_create_card_hold_no_card(self):
        customer_href = self.make_balanced_customer()
        bob = self.make_participant('bob', balanced_customer_href=customer_href,
                                    is_suspicious=False)
        hold, error = create_card_hold(self.db, bob, D('10.00'))
        assert error == 'NoResultFound()'


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
                    u'2091 cents ($20.00 + $0.91 fee = $20.91)',
                    D('20.91'), D('0.91'))
        assert actual == expected

    def test_prep_hit_full_in_rounded_case(self):
        actual = _prep_hit(D('5.00'))
        expected = (1000,
                    u'1000 cents ($9.41 [rounded up from $5.00] + $0.59 fee = $10.00)',
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
