import json
from time import sleep
from unittest.mock import patch

from markupsafe import Markup
from pando.utils import utcnow
import stripe

from liberapay.billing.payday import Payday
from liberapay.constants import DONATION_LIMITS, EPOCH, PAYIN_AMOUNTS, STANDARD_TIPS
from liberapay.exceptions import MissingPaymentAccount, NoSelfTipping
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.payin.common import resolve_amounts, resolve_team_donation
from liberapay.payin.cron import execute_reviewed_payins
from liberapay.payin.paypal import sync_all_pending_payments
from liberapay.payin.prospect import PayinProspect
from liberapay.payin.stripe import settle_charge_and_transfers, try_other_destinations
from liberapay.testing import Harness, EUR, KRW, JPY, USD
from liberapay.testing.emails import EmailHarness


class TestResolveAmounts(Harness):

    def test_resolve_low_amounts(self):
        naive_amounts = {1: EUR('20.00'), 2: EUR('0.01')}
        expected_amounts = {1: EUR('6.00'), 2: EUR('0.01')}
        resolved_amounts = resolve_amounts(EUR('6.01'), naive_amounts)
        assert resolved_amounts == expected_amounts

    def test_resolve_exact_amounts(self):
        naive_amounts = {1: EUR('20.00'), 2: EUR('0.01')}
        expected_amounts = {1: EUR('20.00'), 2: EUR('0.01')}
        resolved_amounts = resolve_amounts(EUR('20.01'), naive_amounts)
        assert resolved_amounts == expected_amounts

    def test_resolve_high_amounts(self):
        naive_amounts = {1: EUR('20.00'), 2: EUR('0.01')}
        expected_amounts = {1: EUR('40.00'), 2: EUR('0.02')}
        resolved_amounts = resolve_amounts(EUR('40.02'), naive_amounts)
        assert resolved_amounts == expected_amounts

    def test_resolve_exact_convergence(self):
        base_amounts = {1: EUR('1.23'), 2: EUR('4.56')}
        convergence_amounts = {1: EUR('7.89'), 2: EUR('0.01')}
        resolved_amounts = resolve_amounts(
            EUR('7.90'), base_amounts, convergence_amounts
        )
        assert resolved_amounts == convergence_amounts

    def test_resolve_exact_convergence_with_minimum_amount(self):
        base_amounts = {1: EUR('1.23'), 2: EUR('4.56')}
        convergence_amounts = {1: EUR('7.89'), 2: EUR('0.01')}
        expected_amounts = {1: EUR('7.90')}
        resolved_amounts = resolve_amounts(
            EUR('7.90'), base_amounts, convergence_amounts, minimum_amount=EUR('0.03'),
        )
        assert resolved_amounts == expected_amounts
        convergence_amounts = {1: EUR('7.89'), 2: EUR('0.01'), 3: EUR('0.01')}
        expected_amounts = {1: EUR('7.89'), 2: EUR('0.02')}
        resolved_amounts = resolve_amounts(
            EUR('7.91'), base_amounts, convergence_amounts, minimum_amount=EUR('0.02'),
            payday_id=1,
        )
        assert resolved_amounts == expected_amounts
        convergence_amounts = {1: EUR('7.89'), 2: EUR('0.01'), 3: EUR('0.01')}
        expected_amounts = {1: EUR('7.89'), 3: EUR('0.02')}
        resolved_amounts = resolve_amounts(
            EUR('7.91'), base_amounts, convergence_amounts, minimum_amount=EUR('0.02'),
            payday_id=2,
        )
        assert resolved_amounts == expected_amounts

    def test_resolve_full_convergence_and_then_some(self):
        base_amounts = {1: EUR('1.23'), 2: EUR('4.56')}
        convergence_amounts = {1: EUR('7.89'), 2: EUR('0.01')}
        expected_amounts = {1: EUR('9.12'), 2: EUR('4.57')}
        resolved_amounts = resolve_amounts(
            EUR('13.69'), base_amounts, convergence_amounts
        )
        assert resolved_amounts == expected_amounts

    def test_resolve_full_convergence_and_then_some_with_maximums(self):
        base_amounts = {1: EUR('1.23'), 2: EUR('4.56'), 3: EUR('0.01')}
        convergence_amounts = {1: EUR('7.89'), 2: EUR('0.01'), 3: EUR('0.01')}
        maximum_amounts = {1: EUR('6.00'), 2: EUR('6.00'), 3: EUR('0.00')}
        expected_amounts = {1: EUR('6.00'), 2: EUR('6.00')}
        resolved_amounts = resolve_amounts(
            EUR('12.00'), base_amounts, convergence_amounts,
            maximum_amounts=maximum_amounts,
        )
        assert resolved_amounts == expected_amounts
        maximum_amounts = {1: EUR('6.00'), 2: EUR('6.01'), 3: EUR('0.00')}
        resolved_amounts = resolve_amounts(
            EUR('12.00'), base_amounts, convergence_amounts,
            maximum_amounts=maximum_amounts,
        )
        assert resolved_amounts == expected_amounts

    def test_resolve_partial_convergence(self):
        base_amounts = {1: EUR('1.23'), 2: EUR('4.56')}
        convergence_amounts = {1: EUR('7.89'), 2: EUR('0.01')}
        expected_amounts = {1: EUR('0.98'), 2: EUR('0.01')}
        resolved_amounts = resolve_amounts(
            EUR('0.99'), base_amounts, convergence_amounts
        )
        assert resolved_amounts == expected_amounts
        convergence_amounts = {1: EUR('0.50'), 2: EUR('0.50')}
        for i in range(1, 10):
            if i % 2 == 1:
                expected_amounts = {1: EUR('0.50'), 2: EUR('0.49')}
            else:
                expected_amounts = {1: EUR('0.49'), 2: EUR('0.50')}
            resolved_amounts = resolve_amounts(
                EUR('0.99'), base_amounts, convergence_amounts, payday_id=i,
            )
            assert resolved_amounts == expected_amounts

    def test_resolve_amounts_with_minimum(self):
        naive_amounts = {1: EUR('10.00'), 2: EUR('0.02')}
        expected_amounts = {1: EUR('5.01')}
        resolved_amounts = resolve_amounts(
            EUR('5.01'), naive_amounts, minimum_amount=EUR('0.02')
        )
        assert resolved_amounts == expected_amounts

    def test_resolve_amounts_with_minimum_rotates_the_winner(self):
        naive_amounts = {1: EUR('0.30'), 2: EUR('0.20'), 3: EUR('0.10')}
        for i in range(1, 10):
            expected_amounts = {(i - 1) % 3 + 1: EUR('0.06')}
            resolved_amounts = resolve_amounts(
                EUR('0.06'), naive_amounts, minimum_amount=EUR('0.05'), payday_id=i,
            )
            assert resolved_amounts == expected_amounts


class TestResolveTeamDonation(Harness):

    def resolve(self, team, provider, payer, payer_country, payment_amount, sepa_only=False):
        tip = self.db.one("""
            SELECT *
              FROM current_tips
             WHERE tipper = %s
               AND tippee = %s
        """, (payer.id, team.id))
        donations = resolve_team_donation(
            self.db, team, provider, payer, payer_country, payment_amount, tip,
            sepa_only=sepa_only,
        )
        if len(donations) == 1:
            assert donations[0].amount == payment_amount
            return donations[0].destination
        else:
            return donations

    def test_resolve_team_donation(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        team = self.make_participant('team', kind='group', accepted_currencies=None)
        alice.set_tip_to(team, EUR('1.00'))

        # Test without payment account
        team.add_member(bob)
        with self.assertRaises(MissingPaymentAccount):
            self.resolve(team, 'stripe', alice, 'FR', EUR('10'))

        # Test without payment account at the requested provider
        stripe_account_bob = self.add_payment_account(bob, 'stripe', country='FR')
        with self.assertRaises(MissingPaymentAccount):
            self.resolve(team, 'paypal', alice, 'US', EUR('10'))

        # Test with a single member and the take set to `auto`
        account = self.resolve(team, 'stripe', alice, 'GB', EUR('7'))
        assert account == stripe_account_bob

        # Test self donation
        bob.set_tip_to(team, EUR('0.06'))
        with self.assertRaises(NoSelfTipping):
            account = self.resolve(team, 'stripe', bob, 'FR', EUR('6'))

        # Test with two members but only one payment account
        team.add_member(carl)
        account = self.resolve(team, 'stripe', alice, 'CH', EUR('8'))
        assert account == stripe_account_bob

        # Test with two members but only one payment account at the requested provider
        paypal_account_carl = self.add_payment_account(carl, 'paypal')
        team.set_take_for(carl, EUR('200.00'), carl)
        account = self.resolve(team, 'stripe', alice, 'BE', EUR('42'))
        assert account == stripe_account_bob
        team.set_take_for(carl, EUR('-1'), carl)
        team.set_take_for(carl, EUR('200.00'), bob)
        account = self.resolve(team, 'paypal', alice, 'BE', EUR('47'))
        assert account == paypal_account_carl
        team.set_take_for(carl, EUR('-1'), bob)

        # Test with two members and both takes set to `auto`
        stripe_account_carl = self.add_payment_account(
            carl, 'stripe', country='JP', default_currency='JPY'
        )
        account = self.resolve(team, 'stripe', alice, 'PL', EUR('5.46'))
        assert account == stripe_account_bob
        account = self.resolve(team, 'paypal', alice, 'PL', EUR('99.9'))
        assert account == paypal_account_carl

        # Test with two members and one non-auto take
        team.set_take_for(bob, EUR('100.00'), bob)
        account = self.resolve(team, 'stripe', alice, 'RU', EUR('50.02'))
        assert account == stripe_account_bob
        account = self.resolve(team, 'paypal', alice, 'RU', EUR('33'))
        assert account == paypal_account_carl

        # Test with two members and two different non-auto takes
        team.set_take_for(carl, EUR('200.00'), carl)
        account = self.resolve(team, 'stripe', alice, 'BR', EUR('10'))
        assert account == stripe_account_carl
        account = self.resolve(team, 'stripe', alice, 'BR', EUR('1'))
        assert account == stripe_account_carl
        account = self.resolve(team, 'paypal', alice, 'BR', EUR('5'))
        assert account == paypal_account_carl

        # Test that self donation is avoided when there are two members
        carl.set_tip_to(team, EUR('17.89'))
        account = self.resolve(team, 'stripe', carl, 'FR', EUR('71.56'))
        assert account == stripe_account_bob

        # Test with a suspended member
        self.db.run("UPDATE participants SET is_suspended = true WHERE id = %s", (carl.id,))
        account = self.resolve(team, 'stripe', alice, 'RU', EUR('7.70'))
        assert account == stripe_account_bob
        self.db.run("UPDATE participants SET is_suspended = false WHERE id = %s", (carl.id,))

        # Check that members are cycled through
        alice_card = ExchangeRoute.insert(
            alice, 'stripe-card', 'x', 'chargeable', remote_user_id='x'
        )
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('2'))
        assert pt.destination == stripe_account_carl.pk
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('1'))
        assert pt.destination == stripe_account_bob.pk
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('4'))
        assert pt.destination == stripe_account_carl.pk
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('10'))
        assert pt.destination == stripe_account_carl.pk
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('2'))
        assert pt.destination == stripe_account_bob.pk

        # Test with two members having SEPA accounts and one non-SEPA
        # We also add the donor to the team, to check that self tipping is avoided.
        stripe_account_carl = self.add_payment_account(
            carl, 'stripe', country='DE', id='acct_DE',
        )
        dana = self.make_participant('dana')
        self.add_payment_account(dana, 'stripe', country='US', default_currency='USD')
        team.add_member(dana)
        self.add_payment_account(alice, 'stripe', country='BE')
        team.add_member(alice)
        payin, payin_transfers = self.make_payin_and_transfer(
            alice_card, team, EUR('6.80'), fee=EUR('0.60')
        )
        assert len(payin_transfers) == 2
        assert payin_transfers[0].amount == EUR('5.40')
        assert payin_transfers[0].destination == stripe_account_bob.pk
        assert payin_transfers[0].unit_amount == EUR('0.87')
        assert payin_transfers[0].n_units == 6
        assert payin_transfers[1].amount == EUR('0.80')
        assert payin_transfers[1].destination == stripe_account_carl.pk
        assert payin_transfers[1].unit_amount == EUR('0.13')
        assert payin_transfers[1].n_units == 6
        # Check that this donation has balanced the takes.
        takes = {t.member: t for t in self.db.all("""
            SELECT member, amount, paid_in_advance
              FROM current_takes
             WHERE team = %s
        """, (team.id,))}
        weeks_of_advance_bob = takes[bob.id].paid_in_advance / takes[bob.id].amount
        weeks_of_advance_carl = takes[carl.id].paid_in_advance / takes[carl.id].amount
        assert weeks_of_advance_bob == weeks_of_advance_carl

        # Test after two paydays
        Payday.start().run()
        self.db.run("UPDATE notifications SET ts = ts - interval '7 days'")
        Payday.start().run()
        payin, payin_transfers = self.make_payin_and_transfer(
            alice_card, team, EUR('3.30'), fee=EUR('0.30')
        )
        assert len(payin_transfers) == 2
        assert payin_transfers[0].amount == EUR('1.00')
        assert payin_transfers[0].destination == stripe_account_bob.pk
        assert payin_transfers[1].amount == EUR('2.00')
        assert payin_transfers[1].destination == stripe_account_carl.pk

        # Test with a transfer currency different than the tip currency
        payin, payin_transfers = self.make_payin_and_transfers(
            alice_card, EUR('10.00'), [(team, USD('12.00'), {})],
        )
        assert len(payin_transfers) == 2
        assert payin_transfers[0].amount == USD('4.00')
        assert payin_transfers[0].destination == stripe_account_bob.pk
        assert payin_transfers[1].amount == USD('8.00')
        assert payin_transfers[1].destination == stripe_account_carl.pk

    def test_resolve_team_donation_sepa_only(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        team = self.make_participant('team', kind='group', accepted_currencies=None)
        alice.set_tip_to(team, EUR('1.00'))

        # Test without payment account
        team.add_member(bob)
        with self.assertRaises(MissingPaymentAccount):
            self.resolve(team, 'stripe', alice, 'FR', EUR('10'), sepa_only=True)

        # Test with a single member and the take set to `auto`
        stripe_account_bob = self.add_payment_account(bob, 'stripe', country='FR')
        account = self.resolve(team, 'stripe', alice, 'GB', EUR('7'), sepa_only=True)
        assert account == stripe_account_bob

        # Test self donation
        bob.set_tip_to(team, EUR('0.06'))
        with self.assertRaises(NoSelfTipping):
            self.resolve(team, 'stripe', bob, 'FR', EUR('6'), sepa_only=True)

        # Test with two members but only one Stripe account
        team.add_member(carl)
        self.add_payment_account(carl, 'paypal')
        account = self.resolve(team, 'stripe', alice, 'CH', EUR('8'), sepa_only=True)
        assert account == stripe_account_bob

        # Test with two members and both takes set to `auto`
        self.add_payment_account(carl, 'stripe', country='JP', default_currency='JPY')
        account = self.resolve(team, 'stripe', alice, 'PL', EUR('5.46'), sepa_only=True)
        assert account == stripe_account_bob

        # Test with two members and one non-auto take
        team.set_take_for(carl, EUR('200.00'), carl)
        account = self.resolve(team, 'stripe', alice, 'RU', EUR('50.02'), sepa_only=True)
        assert account == stripe_account_bob

        # Test with two members and two different non-auto takes
        team.set_take_for(bob, EUR('100.00'), bob)
        account = self.resolve(team, 'stripe', alice, 'BR', EUR('10'), sepa_only=True)
        assert account == stripe_account_bob
        account = self.resolve(team, 'stripe', alice, 'BR', EUR('1'), sepa_only=True)
        assert account == stripe_account_bob

        # Test that self donation is avoided when there are two members
        carl.set_tip_to(team, EUR('17.89'))
        account = self.resolve(team, 'stripe', carl, 'FR', EUR('71.56'), sepa_only=True)
        assert account == stripe_account_bob

        # Test with a suspended member
        self.db.run("UPDATE participants SET is_suspended = true WHERE id = %s", (carl.id,))
        account = self.resolve(team, 'stripe', alice, 'RU', EUR('7.70'), sepa_only=True)
        assert account == stripe_account_bob
        self.db.run("UPDATE participants SET is_suspended = false WHERE id = %s", (carl.id,))

        # Test when the only member the payment can go to has their take at zero
        team.set_take_for(bob, EUR('0'), bob)
        with self.assertRaises(MissingPaymentAccount):
            self.resolve(team, 'stripe', alice, 'CN', EUR('10'), sepa_only=True)


class TestPayinAmountSuggestions(Harness):

    def setUp(self):
        self.alice = self.make_participant('alice')
        self.bob = self.make_participant('bob', accepted_currencies=None)
        self.carl = self.make_participant('carl', accepted_currencies=None)
        self.dana = self.make_participant('dana', accepted_currencies=None)

    def test_minimum_weekly_EUR_tip(self):
        tip_amount = DONATION_LIMITS['EUR']['weekly'][0]
        tip = self.alice.set_tip_to(self.bob, tip_amount)
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == tip_amount
        assert pp.one_months_worth == tip_amount * 5
        assert pp.one_years_worth == tip_amount * 52
        assert pp.twenty_years_worth == pp.one_years_worth * 20
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [EUR('2.00'), EUR('10.00')]

    def test_minimum_monthly_EUR_tip(self):
        tip_amount = DONATION_LIMITS['EUR']['monthly'][0]
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == DONATION_LIMITS['EUR']['weekly'][0]
        assert pp.one_months_worth == tip_amount
        assert pp.one_years_worth == tip_amount * 12
        assert pp.twenty_years_worth == pp.one_years_worth * 20
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [EUR('2.00'), EUR('10.00')]

    def test_minimum_yearly_EUR_tip(self):
        tip_amount = DONATION_LIMITS['EUR']['yearly'][0]
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == DONATION_LIMITS['EUR']['weekly'][0]
        assert pp.one_months_worth == (tip_amount / 12).round()
        assert pp.one_years_worth == tip_amount
        assert pp.twenty_years_worth == pp.one_years_worth * 20
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [pp.min_proposed_amount, pp.twenty_years_worth]

    def test_small_weekly_USD_tip(self):
        tip_amount = STANDARD_TIPS['USD'][1].weekly
        tip = self.alice.set_tip_to(self.bob, tip_amount)
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'USD'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == tip_amount
        assert pp.one_months_worth == tip_amount * 5
        assert pp.one_years_worth == tip_amount * 52
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['USD']
        assert pp.suggested_amounts == [USD('2.00'), USD('13.00'), USD('48.00')]

    def test_small_monthly_USD_tip(self):
        tip_amount = USD('1.00')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'USD'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == USD('0.23')
        assert pp.one_months_worth == tip_amount
        assert pp.one_years_worth == tip_amount * 12
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['USD']
        assert pp.suggested_amounts == [USD('2.00'), USD('12.00'), USD('48.00')]

    def test_small_yearly_USD_tip(self):
        tip_amount = USD('10.00')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'USD'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == USD('0.19')
        assert pp.one_months_worth == USD('0.83')
        assert pp.one_years_worth == tip_amount
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['USD']
        assert pp.suggested_amounts == [
            USD('10.00'), USD('20.00'), USD('50.00')
        ]

    def test_medium_weekly_JPY_tip(self):
        tip_amount = STANDARD_TIPS['JPY'][2].weekly
        tip = self.alice.set_tip_to(self.bob, tip_amount)
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'JPY'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == tip_amount
        assert pp.one_months_worth == tip_amount * 5
        assert pp.one_years_worth == tip_amount * 52
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['JPY']
        assert pp.suggested_amounts == [
            JPY('650'), JPY('1690'), JPY('3380'), JPY('6760')
        ]

    def test_medium_monthly_JPY_tip(self):
        tip_amount = JPY('500')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'JPY'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == JPY('115')
        assert pp.one_months_worth == tip_amount
        assert pp.one_years_worth == tip_amount * 12
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['JPY']
        assert pp.suggested_amounts == [
            JPY('500'), JPY('1500'), JPY('3000'), JPY('6000')
        ]

    def test_medium_yearly_JPY_tip(self):
        tip_amount = JPY('5000')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'JPY'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == JPY('96')
        assert pp.one_months_worth == JPY('417')
        assert pp.one_years_worth == tip_amount
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['JPY']
        assert pp.suggested_amounts == [JPY('5000'), JPY('10000')]

    def test_large_weekly_EUR_tip(self):
        tip_amount = STANDARD_TIPS['EUR'][3].weekly
        tip = self.alice.set_tip_to(self.bob, tip_amount)
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == tip_amount
        assert pp.one_months_worth == tip_amount * 5
        assert pp.one_years_worth == tip_amount * 52
        assert pp.suggested_amounts == [
            EUR('25.00'), EUR('65.00'), EUR('130.00'), EUR('260.00')
        ]

    def test_large_monthly_EUR_tip(self):
        tip_amount = EUR('25.00')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == EUR('5.76')
        assert pp.one_months_worth == tip_amount
        assert pp.one_years_worth == tip_amount * 12
        assert pp.suggested_amounts == [
            EUR('25.00'), EUR('75.00'), EUR('150.00'), EUR('300.00')
        ]

    def test_large_yearly_EUR_tip(self):
        tip_amount = EUR('500.00')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == EUR('9.61')
        assert pp.one_months_worth == EUR('41.67')
        assert pp.one_years_worth == tip_amount
        assert pp.suggested_amounts == [EUR('500.00'), EUR('1000.00')]

    def test_maximum_yearly_EUR_tip(self):
        tip_amount = EUR('5200.00')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        pp = PayinProspect(self.alice, [tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == EUR('100.00')
        assert pp.one_months_worth == EUR('433.33')
        assert pp.one_years_worth == tip_amount
        assert pp.suggested_amounts == [EUR('5200.00')]
        assert pp.max_acceptable_amount == EUR('5200.00')

    def test_two_small_monthly_USD_tips(self):
        tip_amount = USD('1.00')
        tip1 = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        tip2 = self.alice.set_tip_to(self.carl, tip_amount, period='monthly')
        pp = PayinProspect(self.alice, [tip1, tip2], 'stripe')
        assert pp.currency == 'USD'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount * 2
        assert pp.one_weeks_worth == USD('0.46')
        assert pp.one_months_worth == pp.one_periods_worth
        assert pp.one_years_worth == tip_amount * 24
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['USD']
        assert pp.suggested_amounts == [
            USD('2.00'), USD('12.00'), USD('24.00'), USD('48.00')
        ]

    def test_two_medium_yearly_KRW_tips(self):
        tip_amount = KRW('50000')
        tip1 = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        tip2 = self.alice.set_tip_to(self.carl, tip_amount, period='yearly')
        pp = PayinProspect(self.alice, [tip1, tip2], 'stripe')
        assert pp.currency == 'KRW'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount * 2
        assert pp.one_weeks_worth == KRW('1922')
        assert pp.one_months_worth == KRW('8333')
        assert pp.one_years_worth == pp.one_periods_worth
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['KRW']
        assert pp.suggested_amounts == [KRW('100000'), KRW('200000')]

    def test_two_very_different_EUR_tips(self):
        tip1 = self.alice.set_tip_to(self.bob, EUR('0.24'), period='weekly')
        tip2 = self.alice.set_tip_to(self.carl, EUR('240.00'), period='yearly')
        pp = PayinProspect(self.alice, [tip1, tip2], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == EUR('4.86')
        assert pp.one_weeks_worth == pp.one_weeks_worth
        assert pp.one_months_worth == pp.one_weeks_worth * 5
        assert pp.one_years_worth == EUR('252.48')
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [
            EUR('24.25'), EUR('63.12'), EUR('126.24'), EUR('252.48')
        ]

    def test_three_very_different_EUR_tips(self):
        tip1 = self.alice.set_tip_to(self.bob, EUR('0.01'), period='weekly')
        tip2 = self.alice.set_tip_to(self.carl, EUR('1.00'), period='monthly')
        tip3 = self.alice.set_tip_to(self.dana, EUR('5200.00'), period='yearly')
        pp = PayinProspect(self.alice, [tip1, tip2, tip3], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == EUR('434.38')
        assert pp.one_weeks_worth == EUR('100.24')
        assert pp.one_months_worth == pp.one_periods_worth
        assert pp.one_years_worth == EUR('5212.52')
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [
            EUR('434.38'), EUR('1303.13'), EUR('2606.26')
        ]


class TestPayins(Harness):

    def setUp(self):
        super().setUp()
        self.donor = self.make_participant('donor', email='donor@example.com')
        self.creator_0 = self.make_participant(
            'creator_0', email='zero@example.com', accepted_currencies=None
        )
        self.creator_1 = self.make_participant(
            'creator_1', email='alice@example.com', accepted_currencies=None
        )
        self.creator_2 = self.make_participant(
            'creator_2', email='bob@example.com', accepted_currencies=None
        )
        self.creator_3 = self.make_participant(
            'creator_3', email='carl@example.com', accepted_currencies=None
        )

    def tearDown(self):
        self.db.self_check()
        super().tearDown()

    def test_payin_pages_when_currencies_dont_match(self):
        self.add_payment_account(self.creator_1, 'stripe')
        self.add_payment_account(self.creator_2, 'paypal')
        self.add_payment_account(self.creator_3, 'stripe')
        self.add_payment_account(self.creator_3, 'paypal')
        self.donor.set_tip_to(self.creator_1, EUR('11.00'))
        self.donor.set_tip_to(self.creator_2, JPY('1100'))
        self.donor.set_tip_to(self.creator_3, USD('11.00'))

        paypal_path = '/donor/giving/pay/paypal/?beneficiary=%i,%i' % (
            self.creator_2.id, self.creator_3.id
        )
        stripe_path = '/donor/giving/pay/stripe/?beneficiary=%i,%i&method=card' % (
            self.creator_1.id, self.creator_3.id
        )
        r = self.client.GET('/donor/giving/pay/', auth_as=self.donor)
        assert r.code == 200, r.text
        assert str(Markup.escape(paypal_path)) not in r.text
        assert str(Markup.escape(stripe_path)) not in r.text

        r = self.client.GxT(paypal_path, auth_as=self.donor)
        assert r.code == 400, r.text

        r = self.client.GxT(stripe_path, auth_as=self.donor)
        assert r.code == 400, r.text


class TestPayinsPayPal(Harness):

    def setUp(self):
        super().setUp()
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH 1")
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH 1")
        self.donor = self.make_participant('donor', email='donor@example.com')
        self.creator_0 = self.make_participant('creator_0', email='zero@example.com')
        self.creator_1 = self.make_participant('creator_1', email='alice@example.com')
        self.creator_2 = self.make_participant('creator_2', email='bob@example.com')
        self.creator_3 = self.make_participant('creator_3', email='carl@example.com')

    def test_payin_paypal(self):
        self.add_payment_account(self.creator_2, 'paypal', 'US')
        tip = self.donor.set_tip_to(self.creator_2, EUR('0.01'))

        # 1st request: test getting the payment page
        r = self.client.GET(
            '/donor/giving/pay/paypal?beneficiary=%i' % self.creator_2.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

        # 2nd request: initiate the payment
        form_data = {
            'amount': '10.00',
            'currency': 'EUR',
            'tips': str(tip['id'])
        }
        r = self.client.PxST('/donor/giving/pay/paypal', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/paypal/1'
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('10.00')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('10.00')

        # 3rd request: redirect to PayPal
        r = self.client.GxT(
            '/donor/giving/pay/paypal/1', HTTP_ACCEPT_LANGUAGE=b'es-419',
            auth_as=self.donor,
        )
        assert r.code == 302, r.text
        assert r.headers[b'Location'].startswith(b'https://www.sandbox.paypal.com/')
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'awaiting_payer_action'

        # 4th request: execute the payment
        qs = '?token=91V21788MR556192E&PayerID=6C9EQBCEQY4MA'
        r = self.client.GET('/donor/giving/pay/paypal/1' + qs, auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded'
        assert payin.error is None
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pending'
        assert pt.error == 'RECEIVING_PREFERENCE_MANDATES_MANUAL_ACTION'
        assert pt.amount == EUR('10.00')

        # While we're at it, test syncing payments
        sync_all_pending_payments(self.db)

    def test_payin_paypal_invalid_email(self):
        paypal_account_fr = self.add_payment_account(
            self.creator_2, 'paypal', 'FR', id='bad email'
        )
        tip = self.donor.set_tip_to(self.creator_2, EUR('0.25'))

        # 1st request: test getting the payment page
        r = self.client.GET(
            '/donor/giving/pay/paypal?beneficiary=%i' % self.creator_2.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

        # 2nd request: payin creation
        form_data = {
            'amount': '12.00',
            'currency': 'EUR',
            'tips': str(tip['id'])
        }
        r = self.client.PxST(
            '/donor/giving/pay/paypal', form_data,
            auth_as=self.donor, HTTP_CF_IPCOUNTRY='FR'
        )
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/paypal/1'
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('12.00')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('12.00')
        assert pt.destination == paypal_account_fr.pk

        # 3rd request: payment creation fails
        r = self.client.GET('/donor/giving/pay/paypal/1', auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'failed'
        assert payin.error
        assert 'debug_id' in payin.error


class TestPayinsStripe(Harness):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.offset = 2200
        # https://stripe.com/docs/connect/testing
        cls.sepa_direct_debit_token = stripe.Token.create(bank_account=dict(
            country='DE',
            currency='EUR',
            account_number='DE89370400440532013000',
            account_holder_name='Jane Doe',
        ), idempotency_key=f'create_german_bank_account_token_{cls.offset}')
        ba_ch_token = stripe.Token.create(bank_account=dict(
            country='CH',
            currency='CHF',
            account_number='CH9300762011623852957',
            account_holder_name='Foo Bar',
        ), idempotency_key=f'create_swiss_bank_account_token_{cls.offset}')
        acct_ch_token = stripe.Token.create(account=dict(
            business_type='individual',
            individual={
                'address': {
                    'country': 'CH',
                    'city': 'Bern',
                    'postal_code': '3000',
                    'line1': 'address_full_match',
                },
                'dob': {'day': 1, 'month': 1, 'year': 1901},
                'email': 'test-swiss-1@liberapay.com',
                'first_name': 'Foo',
                'last_name': 'Bar',
                'id_number': '000000000',
                'phone': '+41665554433',
            },
            tos_shown_and_accepted=True,
        ), idempotency_key=f'create_swiss_account_token_{cls.offset}')
        cls.acct_switzerland = stripe.Account.create(
            account_token=acct_ch_token.id,
            country='CH',
            type='custom',
            business_profile={
                'mcc': 5734,
                'url': 'https://liberapay.com/',
            },
            capabilities={
                'card_payments': {'requested': True},
                'sepa_debit_payments': {'requested': True},
                'transfers': {'requested': True},
            },
            external_account=ba_ch_token,
            idempotency_key=f'create_swiss_account_{cls.offset}',
        )
        try:
            assert cls.acct_switzerland.capabilities == {
                'card_payments': 'active',
                'sepa_debit_payments': 'active',
                'transfers': 'active',
            }
        except AssertionError:
            print(cls.acct_switzerland.requirements)
            raise

    def setUp(self):
        super().setUp()
        self.__class__.offset += 10
        self.db.run("ALTER SEQUENCE participants_id_seq RESTART WITH %s", (self.offset,))
        self.donor = self.make_participant('donor', email='donor@example.com')
        self.creator_0 = self.make_participant(
            'creator_0', email='zero@example.com', accepted_currencies=None,
            marked_as='okay',
        )
        self.creator_1 = self.make_participant(
            'creator_1', email='alice@example.com', accepted_currencies=None,
            marked_as='okay',
        )
        self.creator_2 = self.make_participant(
            'creator_2', email='bob@example.com', accepted_currencies=None,
            marked_as='okay',
        )
        self.creator_3 = self.make_participant(
            'creator_3', email='carl@example.com', accepted_currencies=None,
            marked_as='okay',
        )
        self.creator_4 = self.make_participant(
            'creator_4', email='david@example.com', accepted_currencies=None,
        )

    def test_00_payin_stripe_card(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe')
        tip = self.donor.set_tip_to(self.creator_1, EUR('0.05'))

        # 1st request: test getting the payment page
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=card&beneficiary=%i' % self.creator_1.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        form_data = {
            'amount': '24.99',
            'currency': 'EUR',
            'keep': 'true',
            'tips': str(tip['id']),
            'token': 'tok_visa',
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('24.99')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('24.99')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded', payin.error
        assert payin.amount_settled == EUR('24.99')
        assert payin.fee == EUR('0.97')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'succeeded'
        assert pt.amount == EUR('24.02')

    def test_02_payin_stripe_card_one_to_many(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe', id=self.acct_switzerland.id)
        self.add_payment_account(self.creator_3, 'stripe')
        self.add_payment_account(self.creator_3, 'paypal')
        tip1 = self.donor.set_tip_to(self.creator_1, JPY('1250'))
        tip3 = self.donor.set_tip_to(self.creator_3, JPY('1250'))

        # 1st request: test getting the payment pages
        expected_uri = '/donor/giving/pay/stripe/?beneficiary=%i,%i&method=card' % (
            self.creator_1.id, self.creator_3.id
        )
        r = self.client.GET('/donor/giving/pay/', auth_as=self.donor)
        assert r.code == 200, r.text
        assert str(Markup.escape(expected_uri)) in r.text
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        form_data = {
            'amount': '10000',
            'currency': 'JPY',
            'tips': '%i,%i' % (tip1['id'], tip3['id']),
            'token': 'tok_jp',
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == JPY('10000')
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'pre'
        assert pt1.amount == JPY('5000')
        assert pt2.status == 'pre'
        assert pt2.amount == JPY('5000')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded', payin.error
        assert payin.amount_settled.currency == 'JPY'
        assert payin.fee.currency == 'JPY'
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        net_amount = payin.amount_settled - payin.fee
        assert pt1.status == 'succeeded'
        assert pt1.amount == (net_amount / 2).round_up()
        assert pt1.remote_id
        assert pt2.status == 'succeeded'
        assert pt2.amount == (net_amount / 2).round_down()

    def test_01_payin_stripe_sdd(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe')
        tip = self.donor.set_tip_to(self.creator_1, EUR('1.00'))

        # 1st request: test getting the payment page
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=sdd&beneficiary=%i' % self.creator_1.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        form_data = {
            'amount': '52.00',
            'currency': 'EUR',
            'tips': str(tip['id']),
            'token': self.sepa_direct_debit_token.id,
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('52.00')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('52.00')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pending', payin.error
        assert payin.amount_settled is None
        assert payin.fee is None
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pending'
        assert pt.amount == EUR('52.00')

        # 4th request: test getting the payment page again
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=sdd&beneficiary=%i' % self.creator_1.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

    def test_03_payin_stripe_sdd_one_to_many(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe', id=self.acct_switzerland.id)
        self.add_payment_account(self.creator_3, 'stripe')
        self.add_payment_account(self.creator_3, 'paypal')
        tip1 = self.donor.set_tip_to(self.creator_1, EUR('12.00'))
        tip3 = self.donor.set_tip_to(self.creator_3, EUR('12.00'))

        # 1st request: test getting the payment pages
        expected_uri = '/donor/giving/pay/stripe/?beneficiary=%i,%i&method=sdd' % (
            self.creator_1.id, self.creator_3.id
        )
        r = self.client.GET('/donor/giving/pay/', auth_as=self.donor)
        assert r.code == 200, r.text
        assert str(Markup.escape(expected_uri)) in r.text
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        sepa_direct_debit_token = stripe.Token.create(bank_account=dict(
            country='FR',
            currency='EUR',
            account_number='FR1420041010050500013M02606',
            account_holder_name='Jane Doe',
        ))
        form_data = {
            'amount': '100.00',
            'currency': 'EUR',
            'keep': 'true',
            'tips': '%i,%i' % (tip1['id'], tip3['id']),
            'token': sepa_direct_debit_token.id,
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('100.00')
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'pre'
        assert pt1.amount == EUR('50.00')
        assert pt2.status == 'pre'
        assert pt2.amount == EUR('50.00')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pending'
        assert payin.amount_settled is None
        assert payin.fee is None
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'pending'
        assert pt1.amount == EUR('50.00')
        assert pt1.remote_id is None
        assert pt2.status == 'pending'
        assert pt2.amount == EUR('50.00')
        assert pt2.remote_id is None

        # 4th request: test getting the payment page again
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

        # 5th request: test getting another payment page now that the donor has connected a bank account
        self.add_payment_account(self.creator_2, 'stripe')
        self.donor.set_tip_to(self.creator_2, EUR('0.50'))
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=sdd&beneficiary=%i' % self.creator_2.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text
        assert "Use another bank account" in r.text

        # 6th request: test getting the receipt before the payment settles
        r = self.client.GxT('/donor/receipts/direct/%i' % payin.id, auth_as=self.donor)
        assert r.code == 404, r.text

        # Settle
        charge = stripe.Charge.retrieve(payin.remote_id)
        if charge.status == 'pending':
            # Wait ten seconds for the payment to succeed.
            sleep(10)
            charge = stripe.Charge.retrieve(payin.remote_id)
        assert charge.status == 'succeeded'
        assert charge.balance_transaction
        payin = settle_charge_and_transfers(self.db, payin, charge)
        assert payin.status == 'succeeded'
        assert payin.amount_settled
        assert payin.fee
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'succeeded'
        assert pt1.amount == EUR('49.83')
        assert pt1.remote_id is not None
        assert pt2.status == 'succeeded'
        assert pt2.amount == EUR('49.82')
        assert pt2.remote_id is None

        # 7th request: test getting the receipt after the payment is settled
        r = self.client.GET('/donor/receipts/direct/%i' % payin.id, auth_as=self.donor)
        assert r.code == 200, r.text
        assert "2606" in r.text

    def test_04_payin_intent_stripe_card(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe')
        tip = self.donor.set_tip_to(self.creator_1, EUR('0.25'))

        # 1st request: test getting the payment page
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=card&beneficiary=%i' % self.creator_1.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        form_data = {
            'amount': '25',
            'currency': 'EUR',
            'keep': 'true',
            'tips': str(tip['id']),
            'stripe_pm_id': 'pm_card_visa',
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('25.00')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('25.00')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded', payin
        assert payin.amount_settled == EUR('25.00')
        assert payin.fee == EUR('0.98')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'succeeded'
        assert pt.amount == EUR('24.02')

        # 4th request: test getting the payment page again
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=card&beneficiary=%i' % self.creator_1.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

        # 5th request: test getting another payment page now that the donor has connected a card
        self.add_payment_account(self.creator_2, 'stripe')
        self.donor.set_tip_to(self.creator_2, EUR('0.50'))
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=card&beneficiary=%i' % self.creator_2.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text
        assert "We will charge your Visa card " in r.text

    def test_05_payin_intent_stripe_card_one_to_many(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe', id=self.acct_switzerland.id)
        self.add_payment_account(self.creator_3, 'stripe')
        self.add_payment_account(self.creator_3, 'paypal')
        tip1 = self.donor.set_tip_to(self.creator_1, EUR('12.50'))
        tip3 = self.donor.set_tip_to(self.creator_3, EUR('12.50'))

        # 1st request: test getting the payment pages
        expected_uri = '/donor/giving/pay/stripe/?beneficiary=%i,%i&method=card' % (
            self.creator_1.id, self.creator_3.id
        )
        r = self.client.GET('/donor/giving/pay/', auth_as=self.donor)
        assert r.code == 200, r.text
        assert str(Markup.escape(expected_uri)) in r.text
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        form_data = {
            'amount': '100.00',
            'currency': 'EUR',
            'tips': '%i,%i' % (tip1['id'], tip3['id']),
            'stripe_pm_id': 'pm_card_jp',
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('100.00')
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'pre'
        assert pt1.amount == EUR('50.00')
        assert pt2.status == 'pre'
        assert pt2.amount == EUR('50.00')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded'
        assert payin.amount_settled == EUR('100.00')
        assert payin.fee == EUR('3.15')
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'succeeded'
        assert pt1.amount == EUR('48.43')
        assert pt1.remote_id
        assert pt2.status == 'succeeded'
        assert pt2.amount == EUR('48.42')

        # 4th request: test getting the payment page again
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

    def test_06_payin_stripe_sdd_to_team(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe', id='acct_1Gv6gnIi3iiNpKFF', country='MY', currency='MYR')
        self.add_payment_account(self.creator_2, 'stripe')
        self.add_payment_account(self.creator_3, 'paypal')
        team = self.make_participant('team', kind='group')
        team.set_take_for(self.creator_1, EUR('10.00'), team)
        team.set_take_for(self.creator_2, EUR('1.00'), team)
        team.set_take_for(self.creator_3, EUR('20.00'), team)
        tip = self.donor.set_tip_to(team, EUR('12.00'))

        # 1st request: test getting the payment pages
        expected_uri = '/donor/giving/pay/stripe/?beneficiary=%i&method=sdd' % team.id
        r = self.client.GET('/donor/giving/pay/', auth_as=self.donor)
        assert r.code == 200, r.text
        assert str(Markup.escape(expected_uri)) in r.text
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        sepa_direct_debit_token = stripe.Token.create(bank_account=dict(
            country='FR',
            currency='EUR',
            account_number='FR1420041010050500013M02606',
            account_holder_name='Jane Doe',
        ))
        form_data = {
            'amount': '100.00',
            'currency': 'EUR',
            'keep': 'true',
            'tips': str(tip['id']),
            'token': sepa_direct_debit_token.id,
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('100.00')
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 1
        pt = payin_transfers[0]
        assert pt.status == 'pre'
        assert pt.amount == EUR('100.00')
        assert pt.recipient == self.creator_1.id

        # 3rd request: execute the payment
        r = self.client.GxT('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
        assert r.code == 302, r.text
        assert r.headers[b'Location'] == b'/donor/giving/pay/stripe/%i' % (self.offset + 1)
        r = self.client.GET('/donor/giving/pay/stripe/%i' % (self.offset + 1), auth_as=self.donor)
        assert r.code == 200, r.text
        payin1, payin2 = self.db.all("SELECT * FROM payins ORDER BY id")
        assert payin1.status == 'failed'
        assert payin1.error.startswith("For 'sepa_debit' payments, we currently require ")
        assert payin2.status == 'pending'
        assert payin2.amount_settled is None
        assert payin2.fee is None
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'failed'
        assert pt1.amount == EUR('100.00')
        assert pt1.remote_id is None
        assert pt2.status == 'pending'
        assert pt2.amount == EUR('100.00')
        assert pt2.remote_id is None
        assert pt2.recipient == self.creator_2.id

        # 4th request: test getting the payment page again
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

        # 5th request: test getting the receipt before the payment settles
        r = self.client.GxT('/donor/receipts/direct/%i' % payin.id, auth_as=self.donor)
        assert r.code == 404, r.text

        # Settle
        charge = stripe.Charge.retrieve(payin2.remote_id)
        if charge.status == 'pending':
            # Wait ten seconds for the payment to succeed.
            sleep(10)
            charge = stripe.Charge.retrieve(payin2.remote_id)
        assert charge.status == 'succeeded'
        assert charge.balance_transaction
        payin = settle_charge_and_transfers(self.db, payin2, charge)
        assert payin.status == 'succeeded'
        assert payin.amount_settled
        assert payin.fee
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'failed'
        assert pt1.amount == EUR('100.00')
        assert pt1.remote_id is None
        assert pt2.status == 'succeeded'
        assert pt2.amount == EUR('99.65')

        # 6th request: test getting the receipt after the payment is settled
        r = self.client.GET('/donor/receipts/direct/%i' % payin.id, auth_as=self.donor)
        assert r.code == 200, r.text
        assert "2606" in r.text

    def test_07_partially_undeliverable_payment(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe', id=self.acct_switzerland.id)
        self.add_payment_account(self.creator_2, 'stripe', id='acct_invalid')
        tip1 = self.donor.set_tip_to(self.creator_1, EUR('12.50'))
        tip3 = self.donor.set_tip_to(self.creator_2, EUR('12.50'))

        # 1st request: test getting the payment pages
        expected_uri = '/donor/giving/pay/stripe/?beneficiary=%i,%i&method=card' % (
            self.creator_1.id, self.creator_2.id
        )
        r = self.client.GET('/donor/giving/pay/', auth_as=self.donor)
        assert r.code == 200, r.text
        assert str(Markup.escape(expected_uri)) in r.text
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        form_data = {
            'amount': '100.00',
            'currency': 'EUR',
            'tips': '%i,%i' % (tip1['id'], tip3['id']),
            'stripe_pm_id': 'pm_card_jp',
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('100.00')
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'pre'
        assert pt1.amount == EUR('50.00')
        assert pt2.status == 'pre'
        assert pt2.amount == EUR('50.00')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
        assert r.code == 200, r.text
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'succeeded'
        assert pt1.amount == EUR('48.43')
        assert pt1.remote_id
        assert pt2.status == 'failed'
        assert pt2.amount == EUR('48.42')
        assert pt2.error == "The recipient's account no longer exists."
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded'
        assert payin.amount_settled == EUR('100.00')
        assert payin.fee == EUR('3.15')
        assert payin.refunded_amount == EUR('50.00')
        creator_2_stripe_account = self.db.one("""
            SELECT *
              FROM payment_accounts
             WHERE participant = %s
               AND provider = 'stripe'
        """, (self.creator_2.id,))
        assert creator_2_stripe_account.is_current is None
        self.creator_2 = self.creator_2.refetch()
        assert self.creator_2.payment_providers == 0

        # 4th request: test getting the payment page again
        r = self.client.GET(expected_uri, auth_as=self.donor)
        assert r.code == 200, r.text

    @patch('stripe.BalanceTransaction.retrieve')
    @patch('stripe.PaymentIntent.create')
    def test_08_alternative_destinations_are_tried(self, pi_create, bt_retrieve):
        self.add_payment_account(self.creator_1, 'stripe', country='IN')
        self.add_payment_account(self.creator_2, 'stripe')
        team = self.make_participant('Team', kind='group')
        self.donor.set_tip_to(team, EUR('1.00'))
        team.set_take_for(self.creator_1, EUR('1.00'), team)
        team.set_take_for(self.creator_2, EUR('0.01'), team)
        donor_card = self.upsert_route(self.donor, 'stripe-card', address='pm_card_visa')
        payin, pt = self.make_payin_and_transfer(
            donor_card, team, EUR('52.00'), status='failed',
            error='As per Indian regulations, blah blah blah',
        )
        pi_create.return_value = stripe.PaymentIntent.construct_from(
            json.loads('''{
              "id": "pi_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "payment_intent",
              "amount": 52000,
              "amount_capturable": 0,
              "amount_received": 52000,
              "application": null,
              "application_fee_amount": null,
              "canceled_at": null,
              "cancellation_reason": null,
              "capture_method": "automatic",
              "charges": {
                "object": "list",
                "data": [
                  {
                    "id": "ch_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "object": "charge",
                    "amount": 52000,
                    "amount_captured": 52000,
                    "amount_refunded": 0,
                    "application": null,
                    "application_fee": null,
                    "application_fee_amount": null,
                    "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "billing_details": {
                      "address": {
                        "city": null,
                        "country": null,
                        "line1": null,
                        "line2": null,
                        "postal_code": "41224",
                        "state": null
                      },
                      "email": null,
                      "name": null,
                      "phone": null
                    },
                    "calculated_statement_descriptor": "Stripe Liberapay XXXX",
                    "captured": true,
                    "created": 1627549263,
                    "currency": "eur",
                    "customer": null,
                    "description": null,
                    "disputed": false,
                    "failure_code": null,
                    "failure_message": null,
                    "fraud_details": {},
                    "invoice": null,
                    "livemode": false,
                    "metadata": {},
                    "on_behalf_of": null,
                    "order": null,
                    "outcome": {
                      "network_status": "approved_by_network",
                      "reason": null,
                      "risk_level": "normal",
                      "risk_score": 64,
                      "seller_message": "Payment complete.",
                      "type": "authorized"
                    },
                    "paid": true,
                    "payment_intent": "pi_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "payment_method": "pm_card_visa",
                    "payment_method_details": {
                      "card": {
                        "brand": "visa",
                        "checks": {
                          "address_line1_check": null,
                          "address_postal_code_check": "pass",
                          "cvc_check": "pass"
                        },
                        "country": "US",
                        "exp_month": 12,
                        "exp_year": 2025,
                        "fingerprint": "812lueijl0oPjCom",
                        "funding": "credit",
                        "installments": null,
                        "last4": "4242",
                        "network": "visa",
                        "three_d_secure": null,
                        "wallet": null
                      },
                      "type": "card"
                    },
                    "receipt_email": null,
                    "receipt_number": null,
                    "receipt_url": "https://pay.stripe.com/receipts/[truncated]",
                    "refunded": false,
                    "refunds": {
                      "object": "list",
                      "data": [],
                      "has_more": false,
                      "url": "/v1/charges/ch_XXXXXXXXXXXXXXXXXXXXXXXX/refunds"
                    },
                    "review": null,
                    "shipping": null,
                    "source_transfer": null,
                    "statement_descriptor": null,
                    "statement_descriptor_suffix": null,
                    "status": "succeeded",
                    "transfer_data": null,
                    "transfer_group": null
                  }
                ],
                "has_more": false,
                "url": "/v1/charges?payment_intent=pi_XXXXXXXXXXXXXXXXXXXXXXXX"
              },
              "client_secret": null,
              "confirmation_method": "automatic",
              "created": 1627549243,
              "currency": "eur",
              "customer": null,
              "description": null,
              "invoice": null,
              "last_payment_error": null,
              "livemode": false,
              "metadata": {},
              "next_action": null,
              "on_behalf_of": null,
              "payment_method": "pm_card_visa",
              "payment_method_options": {
                "card": {
                  "installments": null,
                  "network": null,
                  "request_three_d_secure": "automatic"
                }
              },
              "payment_method_types": [
                "card"
              ],
              "receipt_email": null,
              "review": null,
              "setup_future_usage": null,
              "shipping": null,
              "statement_descriptor": null,
              "statement_descriptor_suffix": null,
              "status": "succeeded",
              "transfer_data": null,
              "transfer_group": null
            }'''),
            stripe.api_key
        )
        bt_retrieve.return_value = stripe.BalanceTransaction.construct_from(
            json.loads('''{
              "amount": 52000,
              "available_on": 1564617600,
              "created": 1564038239,
              "currency": "eur",
              "description": null,
              "exchange_rate": null,
              "fee": 111,
              "fee_details": [
                {
                  "amount": 111,
                  "application": null,
                  "currency": "eur",
                  "description": "Stripe processing fees",
                  "type": "stripe_fee"
                }
              ],
              "id": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
              "net": 51899,
              "object": "balance_transaction",
              "source": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "status": "pending",
              "type": "payment"
            }'''),
            stripe.api_key
        )
        payin2 = try_other_destinations(self.db, payin, self.donor, None)[0]
        assert payin2.status == 'succeeded'
        pt2 = self.db.one("SELECT * FROM payin_transfers WHERE payin = %s", (payin2.id,))
        assert pt2.recipient == self.creator_2.id
        assert pt2.status == 'succeeded'

    def test_09_payin_stripe_sdd_fraud_review(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_4, 'stripe')
        tip = self.donor.set_tip_to(self.creator_4, EUR('1.00'))

        # 1st request: test getting the payment page
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=sdd&beneficiary=%i' % self.creator_4.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        sepa_direct_debit_token = stripe.Token.create(bank_account=dict(
            country='FR',
            currency='EUR',
            account_number='FR1420041010050500013M02606',
            account_holder_name='Jane Doe',
        ))
        form_data = {
            'amount': '52.00',
            'currency': 'EUR',
            'tips': str(tip['id']),
            'token': sepa_direct_debit_token.id,
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/%i' % self.offset
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('52.00')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('52.00')

        # 3rd request: initiate the payment
        # 4th request: check that refreshing the page doesn't change anything
        for i in range(2):
            r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
            assert r.code == 200, r.text
            payin = self.db.one("SELECT * FROM payins")
            assert payin.status == 'awaiting_review', payin.error
            assert payin.error is None
            assert payin.remote_id is None
            assert payin.amount_settled is None
            assert payin.fee is None
            pt = self.db.one("SELECT * FROM payin_transfers")
            assert pt.status == 'awaiting_review'
            assert pt.amount == EUR('52.00')
            assert "It will be submitted to your bank at a later time" in r.text, r.text

        # Mark the recipient as fraud.
        with self.db.get_cursor() as c:
            c.run("UPDATE participants SET marked_as = 'fraud' WHERE username = 'creator_4'")
            self.creator_4.add_event(c, 'flags_changed', {"marked_as": "fraud"})
        # Check that `execute_reviewed_payins` doesn't immediately cancel the payment.
        execute_reviewed_payins()
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'awaiting_review', payin.error
        # Check that `execute_reviewed_payins` does call `charge` after a while.
        self.db.run("UPDATE events SET ts = ts - interval '1 day'")
        with patch('liberapay.payin.cron.charge') as charge:
            execute_reviewed_payins()
            assert charge.call_count == 1

        # 5th request: get the payment page a day later, it should cancel the payment
        # 6th request: check that refreshing the page doesn't change anything
        for i in range(2):
            r = self.client.GET('/donor/giving/pay/stripe/%i' % self.offset, auth_as=self.donor)
            assert r.code == 200, r.text
            payin = self.db.one("SELECT * FROM payins")
            assert payin.status == 'failed', payin.error
            assert payin.error == "canceled"
            assert payin.remote_id is None
            assert payin.amount_settled is None
            assert payin.fee is None
            pt = self.db.one("SELECT * FROM payin_transfers")
            assert pt.status == 'failed'
            assert pt.error == "canceled because the destination account is blocked"


class TestRefundsStripe(EmailHarness):

    def setUp(self):
        super().setUp()
        self._stripe_callback_secret = getattr(
            self.website.app_conf, 'stripe_callback_secret', None
        )
        self.website.app_conf.stripe_callback_secret = 'fake'

    def tearDown(self):
        self.website.app_conf.stripe_callback_secret = self._stripe_callback_secret
        super().tearDown()

    @patch('stripe.BalanceTransaction.retrieve')
    @patch('stripe.Source.retrieve')
    @patch('stripe.Transfer.modify')
    @patch('stripe.Transfer.retrieve')
    @patch('stripe.Webhook.construct_event')
    def test_refunded_destination_charge(
        self, construct_event, tr_retrieve, tr_modify, source_retrieve, bt_retrieve
    ):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob')
        route = self.upsert_route(alice, 'stripe-card')
        alice.set_tip_to(bob, EUR('2.46'))
        payin, pt = self.make_payin_and_transfer(
            route, bob, EUR(400), fee=EUR('3.45'),
            remote_id='py_XXXXXXXXXXXXXXXXXXXXXXXX',
            pt_extra=dict(remote_id='tr_XXXXXXXXXXXXXXXXXXXXXXXX'),
        )
        assert pt.amount == EUR('396.55')
        tip = alice.get_tip_to(bob)
        assert tip.paid_in_advance == pt.amount
        params = dict(payin_id=payin.id, recent_timestamp=(utcnow() - EPOCH).total_seconds())
        construct_event.return_value = stripe.Event.construct_from(
            json.loads('''{
              "id": "evt_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "event",
              "api_version": "2018-05-21",
              "created": 1564297230,
              "data": {
                "object": {
                  "id": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "object": "charge",
                  "amount": 40000,
                  "amount_refunded": 40000,
                  "application": null,
                  "application_fee": null,
                  "application_fee_amount": null,
                  "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "billing_details": {
                    "address": {
                      "city": null,
                      "country": "FR",
                      "line1": null,
                      "line2": null,
                      "postal_code": null,
                      "state": null
                    },
                    "email": "xxxxxxxxx@outlook.fr",
                    "name": "Jane Doe",
                    "phone": null
                  },
                  "captured": true,
                  "created": 1563594672,
                  "currency": "eur",
                  "customer": "cus_XXXXXXXXXXXXXX",
                  "description": null,
                  "destination": "acct_XXXXXXXXXXXXXXXX",
                  "dispute": null,
                  "failure_code": null,
                  "failure_message": null,
                  "fraud_details": {
                  },
                  "invoice": null,
                  "livemode": false,
                  "metadata": {
                    "payin_id": "%(payin_id)s"
                  },
                  "on_behalf_of": "acct_XXXXXXXXXXXXXXXX",
                  "order": null,
                  "outcome": {
                    "network_status": "approved_by_network",
                    "reason": null,
                    "risk_level": "not_assessed",
                    "seller_message": "Payment complete.",
                    "type": "authorized"
                  },
                  "paid": true,
                  "payment_intent": null,
                  "payment_method": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "payment_method_details": {
                    "sepa_debit": {
                      "bank_code": "12345",
                      "branch_code": "10000",
                      "country": "FR",
                      "fingerprint": "XXXXXXXXXXXXXXXX",
                      "last4": "0000"
                    },
                    "type": "sepa_debit"
                  },
                  "receipt_email": null,
                  "receipt_number": null,
                  "receipt_url": "https://pay.stripe.com/receipts/...",
                  "refunded": true,
                  "refunds": {
                    "object": "list",
                    "data": [
                      {
                        "id": "pyr_XXXXXXXXXXXXXXXXXXXXXXXX",
                        "object": "refund",
                        "amount": 40000,
                        "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                        "charge": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
                        "created": %(recent_timestamp)i,
                        "currency": "eur",
                        "metadata": {
                        },
                        "reason": "fraudulent",
                        "receipt_number": null,
                        "source_transfer_reversal": null,
                        "status": "pending",
                        "transfer_reversal": null
                      }
                    ],
                    "has_more": false,
                    "total_count": 1,
                    "url": "/v1/charges/py_XXXXXXXXXXXXXXXXXXXXXXXX/refunds"
                  },
                  "review": null,
                  "shipping": null,
                  "source": {
                    "id": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "object": "source",
                    "amount": null,
                    "client_secret": "src_client_secret_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "created": 1563594673,
                    "currency": "eur",
                    "customer": "cus_XXXXXXXXXXXXXX",
                    "flow": "none",
                    "livemode": false,
                    "mandate": {
                      "acceptance": {
                        "date": null,
                        "ip": null,
                        "offline": null,
                        "online": null,
                        "status": "pending",
                        "type": null,
                        "user_agent": null
                      },
                      "amount": null,
                      "currency": null,
                      "interval": "variable",
                      "notification_method": "none",
                      "reference": "XXXXXXXXXXXXXXXX",
                      "url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
                    },
                    "metadata": {
                    },
                    "owner": {
                      "address": {
                        "city": null,
                        "country": "FR",
                        "line1": null,
                        "line2": null,
                        "postal_code": null,
                        "state": null
                      },
                      "email": "xxxxxxxxx@outlook.fr",
                      "name": "Jane Doe",
                      "phone": null,
                      "verified_address": null,
                      "verified_email": null,
                      "verified_name": null,
                      "verified_phone": null
                    },
                    "sepa_debit": {
                      "last4": "0000",
                      "bank_code": "12345",
                      "branch_code": "10000",
                      "fingerprint": "XXXXXXXXXXXXXXXX",
                      "country": "FR",
                      "mandate_reference": "XXXXXXXXXXXXXXXX",
                      "mandate_url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
                    },
                    "statement_descriptor": null,
                    "status": "chargeable",
                    "type": "sepa_debit",
                    "usage": "reusable"
                  },
                  "source_transfer": null,
                  "statement_descriptor": "Liberapay %(payin_id)s",
                  "status": "succeeded",
                  "transfer": "tr_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "transfer_data": {
                    "amount": null,
                    "destination": "acct_XXXXXXXXXXXXXXXX"
                  },
                  "transfer_group": "group_py_XXXXXXXXXXXXXXXXXXXXXXXX"
                }
              },
              "livemode": false,
              "previous_attributes": {
                "amount_refunded": 0,
                "refunded": false,
                "refunds": {
                  "data": [
                  ],
                  "total_count": 0
                }
              },
              "type": "charge.refunded"
            }''' % params),
            stripe.api_key
        )
        bt_retrieve.return_value = stripe.BalanceTransaction.construct_from(
            json.loads('''{
              "amount": 40000,
              "available_on": 1564617600,
              "created": 1564038239,
              "currency": "eur",
              "description": null,
              "exchange_rate": null,
              "fee": 345,
              "fee_details": [
                {
                  "amount": 345,
                  "application": null,
                  "currency": "eur",
                  "description": "Stripe processing fees",
                  "type": "stripe_fee"
                }
              ],
              "id": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
              "net": 39655,
              "object": "balance_transaction",
              "source": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "status": "pending",
              "type": "payment"
            }'''),
            stripe.api_key
        )
        tr_retrieve.return_value = stripe.Transfer.construct_from(
            json.loads('''{
              "amount": 40000,
              "amount_reversed": 40000,
              "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
              "created": 1564038240,
              "currency": "eur",
              "description": null,
              "destination": "acct_XXXXXXXXXXXXXXXX",
              "destination_payment": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "id": "tr_XXXXXXXXXXXXXXXXXXXXXXXX",
              "livemode": false,
              "metadata": {},
              "object": "transfer",
              "reversals": {
                "data": [
                  {
                    "amount": 39655,
                    "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "created": %(recent_timestamp)i,
                    "currency": "eur",
                    "destination_payment_refund": "pyr_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "id": "trr_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "metadata": {},
                    "object": "transfer_reversal",
                    "source_refund": "pyr_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "transfer": "tr_XXXXXXXXXXXXXXXXXXXXXXXX"
                  },
                  {
                    "amount": 345,
                    "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "created": 1564038243,
                    "currency": "eur",
                    "destination_payment_refund": "pyr_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "id": "trr_XXXXXXXXXXXXXXXXXXXXXXXY",
                    "metadata": {
                      "payin_id": "%(payin_id)s"
                    },
                    "object": "transfer_reversal",
                    "source_refund": null,
                    "transfer": "tr_XXXXXXXXXXXXXXXXXXXXXXXX"
                  }
                ],
                "has_more": false,
                "object": "list",
                "total_count": 2,
                "url": "/v1/transfers/tr_XXXXXXXXXXXXXXXXXXXXXXXX/reversals"
              },
              "reversed": true,
              "source_transaction": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "source_type": "card",
              "transfer_group": "group_py_XXXXXXXXXXXXXXXXXXXXXXXX"
            }''' % params),
            stripe.api_key
        )
        self.db.run("UPDATE payins SET ctime = ctime - interval '24 hours'")
        r = self.client.POST('/callbacks/stripe', {}, HTTP_STRIPE_SIGNATURE='fake')
        assert r.code == 200
        assert r.text == 'OK'
        payin = self.db.one("SELECT * FROM payins WHERE id = %s", (payin.id,))
        assert payin.status == 'succeeded'
        assert payin.refunded_amount == EUR('400.00')
        pt = self.db.one("SELECT * FROM payin_transfers WHERE id = %s", (pt.id,))
        assert pt.status == 'succeeded'
        assert pt.reversed_amount == EUR('396.55')
        refund = self.db.one(
            "SELECT * FROM payin_refunds WHERE payin = %s", (payin.id,)
        )
        assert refund.remote_id == 'pyr_XXXXXXXXXXXXXXXXXXXXXXXX'
        assert refund.amount == EUR('400.00')
        assert refund.reason == 'fraud'
        assert refund.description is None
        assert refund.status == 'pending'
        assert refund.error is None
        reversal = self.db.one(
            "SELECT * FROM payin_transfer_reversals WHERE payin_transfer = %s",
            (pt.id,)
        )
        assert reversal.remote_id == 'trr_XXXXXXXXXXXXXXXXXXXXXXXX'
        assert reversal.payin_refund == refund.id
        assert reversal.amount == EUR('396.55')
        tip = alice.get_tip_to(bob)
        assert tip.paid_in_advance == 0
        # Check that a notification was sent
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['subject'] == "A refund of €400.00 has been initiated"
        # Check that the receipt for this payment has been voided
        source_retrieve.return_value = stripe.Source.construct_from(
            json.loads('''{
              "id": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "source",
              "amount": null,
              "created": 1563594673,
              "currency": "eur",
              "customer": "cus_XXXXXXXXXXXXXX",
              "flow": "none",
              "livemode": false,
              "owner": {
                "address": {
                  "city": null,
                  "country": "FR",
                  "line1": null,
                  "line2": null,
                  "postal_code": null,
                  "state": null
                },
                "email": "xxxxxxxxx@outlook.fr",
                "name": "Jane Doe",
                "phone": null,
                "verified_address": null,
                "verified_email": null,
                "verified_name": null,
                "verified_phone": null
              },
              "sepa_debit": {
                "last4": "0000",
                "bank_code": "12345",
                "branch_code": "10000",
                "fingerprint": "XXXXXXXXXXXXXXXX",
                "country": "FR",
                "mandate_reference": "XXXXXXXXXXXXXXXX",
                "mandate_url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
              },
              "statement_descriptor": null,
              "status": "chargeable",
              "type": "sepa_debit",
              "usage": "reusable"
            }'''),
            stripe.api_key
        )
        r = self.client.GET('/alice/receipts/direct/%i' % payin.id, auth_as=alice)
        assert r.code == 200
        assert ' fully refunded ' in r.text

    @patch('stripe.BalanceTransaction.retrieve')
    @patch('stripe.Source.retrieve')
    @patch('stripe.Transfer.create_reversal')
    @patch('stripe.Transfer.modify')
    @patch('stripe.Transfer.retrieve')
    @patch('stripe.Webhook.construct_event')
    def test_refunded_split_charge(
        self, construct_event, tr_retrieve, tr_modify, tr_create_reversal,
        source_retrieve, bt_retrieve
    ):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe', id='acct_XXXXXXXXXXXXXXXX')
        LiberapayOrg = self.make_participant('LiberapayOrg')
        self.add_payment_account(LiberapayOrg, 'stripe', id='acct_1ChyayFk4eGpfLOC')
        alice.set_tip_to(bob, EUR('1.00'))
        alice.set_tip_to(LiberapayOrg, EUR('1.00'))
        route = self.upsert_route(alice, 'stripe-card')
        payin, transfers = self.make_payin_and_transfers(
            route, EUR(400),
            [
                (bob, EUR(200), {'remote_id': 'tr_XXXXXXXXXXXXXXXXXXXXXXXX'}),
                (LiberapayOrg, EUR(200), {'remote_id': None}),
            ],
            remote_id='py_XXXXXXXXXXXXXXXXXXXXXXXX',
        )
        tip1 = alice.get_tip_to(bob)
        tip2 = alice.get_tip_to(LiberapayOrg)
        assert tip1.paid_in_advance == transfers[0].amount
        assert tip2.paid_in_advance == transfers[1].amount
        params = dict(payin_id=payin.id, recent_timestamp=(utcnow() - EPOCH).total_seconds())
        construct_event.return_value = stripe.Event.construct_from(
            json.loads('''{
              "id": "evt_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "event",
              "api_version": "2018-05-21",
              "created": 1564297230,
              "data": {
                "object": {
                  "id": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "object": "charge",
                  "amount": 40000,
                  "amount_refunded": 40000,
                  "application": null,
                  "application_fee": null,
                  "application_fee_amount": null,
                  "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "billing_details": {
                    "address": {
                      "city": null,
                      "country": "FR",
                      "line1": null,
                      "line2": null,
                      "postal_code": null,
                      "state": null
                    },
                    "email": "xxxxxxxxx@outlook.fr",
                    "name": "Jane Doe",
                    "phone": null
                  },
                  "captured": true,
                  "created": 1563594672,
                  "currency": "eur",
                  "customer": "cus_XXXXXXXXXXXXXX",
                  "description": null,
                  "destination": null,
                  "dispute": null,
                  "failure_code": null,
                  "failure_message": null,
                  "fraud_details": {
                  },
                  "invoice": null,
                  "livemode": false,
                  "metadata": {
                    "payin_id": "%(payin_id)s"
                  },
                  "on_behalf_of": null,
                  "order": null,
                  "outcome": {
                    "network_status": "approved_by_network",
                    "reason": null,
                    "risk_level": "not_assessed",
                    "seller_message": "Payment complete.",
                    "type": "authorized"
                  },
                  "paid": true,
                  "payment_intent": null,
                  "payment_method": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "payment_method_details": {
                    "sepa_debit": {
                      "bank_code": "12345",
                      "branch_code": "10000",
                      "country": "FR",
                      "fingerprint": "XXXXXXXXXXXXXXXX",
                      "last4": "0000"
                    },
                    "type": "sepa_debit"
                  },
                  "receipt_email": null,
                  "receipt_number": null,
                  "receipt_url": "https://pay.stripe.com/receipts/...",
                  "refunded": true,
                  "refunds": {
                    "object": "list",
                    "data": [
                      {
                        "id": "pyr_XXXXXXXXXXXXXXXXXXXXXXXX",
                        "object": "refund",
                        "amount": 40000,
                        "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                        "charge": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
                        "created": %(recent_timestamp)i,
                        "currency": "eur",
                        "metadata": {
                        },
                        "reason": "fraudulent",
                        "receipt_number": null,
                        "source_transfer_reversal": null,
                        "status": "pending",
                        "transfer_reversal": null
                      }
                    ],
                    "has_more": false,
                    "total_count": 1,
                    "url": "/v1/charges/py_XXXXXXXXXXXXXXXXXXXXXXXX/refunds"
                  },
                  "review": null,
                  "shipping": null,
                  "source": {
                    "id": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "object": "source",
                    "amount": null,
                    "client_secret": "src_client_secret_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "created": 1563594673,
                    "currency": "eur",
                    "customer": "cus_XXXXXXXXXXXXXX",
                    "flow": "none",
                    "livemode": false,
                    "mandate": {
                      "acceptance": {
                        "date": null,
                        "ip": null,
                        "offline": null,
                        "online": null,
                        "status": "pending",
                        "type": null,
                        "user_agent": null
                      },
                      "amount": null,
                      "currency": null,
                      "interval": "variable",
                      "notification_method": "none",
                      "reference": "XXXXXXXXXXXXXXXX",
                      "url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
                    },
                    "metadata": {
                    },
                    "owner": {
                      "address": {
                        "city": null,
                        "country": "FR",
                        "line1": null,
                        "line2": null,
                        "postal_code": null,
                        "state": null
                      },
                      "email": "xxxxxxxxx@outlook.fr",
                      "name": "Jane Doe",
                      "phone": null,
                      "verified_address": null,
                      "verified_email": null,
                      "verified_name": null,
                      "verified_phone": null
                    },
                    "sepa_debit": {
                      "last4": "0000",
                      "bank_code": "12345",
                      "branch_code": "10000",
                      "fingerprint": "XXXXXXXXXXXXXXXX",
                      "country": "FR",
                      "mandate_reference": "XXXXXXXXXXXXXXXX",
                      "mandate_url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
                    },
                    "statement_descriptor": null,
                    "status": "chargeable",
                    "type": "sepa_debit",
                    "usage": "reusable"
                  },
                  "source_transfer": null,
                  "statement_descriptor": "Liberapay %(payin_id)s",
                  "status": "succeeded",
                  "transfer": null,
                  "transfer_group": "group_py_XXXXXXXXXXXXXXXXXXXXXXXX"
                }
              },
              "livemode": false,
              "previous_attributes": {
                "amount_refunded": 0,
                "refunded": false,
                "refunds": {
                  "data": [
                  ],
                  "total_count": 0
                }
              },
              "type": "charge.refunded"
            }''' % params),
            stripe.api_key
        )
        bt_retrieve.return_value = stripe.BalanceTransaction.construct_from(
            json.loads('''{
              "amount": 40000,
              "available_on": 1564617600,
              "created": 1564038239,
              "currency": "eur",
              "description": null,
              "exchange_rate": null,
              "fee": 0,
              "fee_details": [],
              "id": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
              "net": 40000,
              "object": "balance_transaction",
              "source": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "status": "pending",
              "type": "payment"
            }'''),
            stripe.api_key
        )
        tr_create_reversal.return_value = stripe.Reversal.construct_from(
            json.loads('''{
              "id": "trr_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "transfer_reversal",
              "amount": 100,
              "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXY",
              "created": 1564297245,
              "currency": "eur",
              "destination_payment_refund": null,
              "metadata": {},
              "source_refund": null,
              "transfer": "po_XXXXXXXXXXXXXXXXXXXXXXXX"
            }'''),
            stripe.api_key
        )
        tr_retrieve.return_value = stripe.Transfer.construct_from(
            json.loads('''{
              "amount": 20000,
              "amount_reversed": 0,
              "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
              "created": 1564038240,
              "currency": "eur",
              "description": null,
              "destination": "acct_XXXXXXXXXXXXXXXX",
              "destination_payment": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "id": "tr_XXXXXXXXXXXXXXXXXXXXXXXX",
              "livemode": false,
              "metadata": {},
              "object": "transfer",
              "reversals": {
                "data": [],
                "has_more": false,
                "object": "list",
                "url": "/v1/transfers/tr_XXXXXXXXXXXXXXXXXXXXXXXX/reversals"
              },
              "reversed": false,
              "source_transaction": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "source_type": "card",
              "transfer_group": "group_py_XXXXXXXXXXXXXXXXXXXXXXXX"
            }''' % params),
            stripe.api_key
        )
        self.db.run("UPDATE payins SET ctime = ctime - interval '24 hours'")
        r = self.client.POST('/callbacks/stripe', {}, HTTP_STRIPE_SIGNATURE='fake')
        assert r.code == 200
        assert r.text == 'OK'
        payin = self.db.one("SELECT * FROM payins WHERE id = %s", (payin.id,))
        assert payin.status == 'succeeded'
        assert payin.refunded_amount == EUR('400.00')
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        for pt in payin_transfers:
            assert pt.status == 'succeeded'
            assert pt.reversed_amount == EUR('200.00')
        refund = self.db.one(
            "SELECT * FROM payin_refunds WHERE payin = %s", (payin.id,)
        )
        assert refund.remote_id == 'pyr_XXXXXXXXXXXXXXXXXXXXXXXX'
        assert refund.amount == EUR('400.00')
        assert refund.reason == 'fraud'
        assert refund.description is None
        assert refund.status == 'pending'
        assert refund.error is None
        reversal = self.db.one("SELECT * FROM payin_transfer_reversals")
        assert reversal.remote_id == 'trr_XXXXXXXXXXXXXXXXXXXXXXXX'
        assert reversal.payin_refund == refund.id
        assert reversal.amount == EUR('200.00')
        tip1 = alice.get_tip_to(bob)
        tip2 = alice.get_tip_to(LiberapayOrg)
        assert tip1.paid_in_advance == 0
        assert tip2.paid_in_advance == 0
        # Check that a notification was sent
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['subject'] == "A refund of €400.00 has been initiated"
        # Check that the receipt for this payment has been voided
        source_retrieve.return_value = stripe.Source.construct_from(
            json.loads('''{
              "id": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "source",
              "amount": null,
              "created": 1563594673,
              "currency": "eur",
              "customer": "cus_XXXXXXXXXXXXXX",
              "flow": "none",
              "livemode": false,
              "owner": {
                "address": {
                  "city": null,
                  "country": "FR",
                  "line1": null,
                  "line2": null,
                  "postal_code": null,
                  "state": null
                },
                "email": "xxxxxxxxx@outlook.fr",
                "name": "Jane Doe",
                "phone": null,
                "verified_address": null,
                "verified_email": null,
                "verified_name": null,
                "verified_phone": null
              },
              "sepa_debit": {
                "last4": "0000",
                "bank_code": "12345",
                "branch_code": "10000",
                "fingerprint": "XXXXXXXXXXXXXXXX",
                "country": "FR",
                "mandate_reference": "XXXXXXXXXXXXXXXX",
                "mandate_url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
              },
              "statement_descriptor": null,
              "status": "chargeable",
              "type": "sepa_debit",
              "usage": "reusable"
            }'''),
            stripe.api_key
        )
        r = self.client.GET('/alice/receipts/direct/%i' % payin.id, auth_as=alice)
        assert r.code == 200
        assert ' fully refunded ' in r.text

    @patch('stripe.BalanceTransaction.retrieve')
    @patch('stripe.Charge.retrieve')
    @patch('stripe.Source.detach')
    @patch('stripe.Source.retrieve')
    @patch('stripe.Transfer.create_reversal')
    @patch('stripe.Transfer.modify')
    @patch('stripe.Transfer.retrieve')
    @patch('stripe.Webhook.construct_event')
    def test_charge_dispute(
        self, construct_event, tr_retrieve, tr_modify, create_reversal, source_retrieve,
        source_detach, ch_retrieve, bt_retrieve,
    ):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe', id='acct_XXXXXXXXXXXXXXXX')
        LiberapayOrg = self.make_participant('LiberapayOrg')
        self.add_payment_account(LiberapayOrg, 'stripe', id='acct_1ChyayFk4eGpfLOC')
        alice.set_tip_to(bob, EUR('3.96'))
        alice.set_tip_to(LiberapayOrg, EUR('3.96'))
        route = self.upsert_route(alice, 'stripe-card')
        payin, transfers = self.make_payin_and_transfers(
            route, EUR(400),
            [
                (bob, EUR(200), {'remote_id': 'tr_XXXXXXXXXXXXXXXXXXXXXXXX'}),
                (LiberapayOrg, EUR(200), {'remote_id': None}),
            ],
            remote_id='py_XXXXXXXXXXXXXXXXXXXXXXXX',
        )
        tip1 = alice.get_tip_to(bob)
        tip2 = alice.get_tip_to(LiberapayOrg)
        assert tip1.paid_in_advance == transfers[0].amount
        assert tip2.paid_in_advance == transfers[1].amount
        params = dict(
            payin_id=payin.id,
            payin_transfer_id=[tr.id for tr in transfers if tr.remote_id][0],
            recent_timestamp=(utcnow() - EPOCH).total_seconds(),
        )
        construct_event.return_value = stripe.Event.construct_from(
            json.loads('''{
              "id": "evt_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "event",
              "api_version": "2018-05-21",
              "created": %(recent_timestamp)s,
              "data": {
                "object": {
                  "id": "dp_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "object": "dispute",
                  "amount": 40000,
                  "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXY",
                  "balance_transactions": [],
                  "charge": "ch_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "created": %(recent_timestamp)s,
                  "currency": "eur",
                  "evidence": {},
                  "evidence_details": {},
                  "is_charge_refundable": false,
                  "livemode": false,
                  "metadata": {},
                  "reason": "general",
                  "status": "lost"
                }
              },
              "livemode": false,
              "type": "charge.dispute.lost"
            }''' % params),
            stripe.api_key
        )
        ch_retrieve.return_value = stripe.Charge.construct_from(
            json.loads('''{
              "id": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "charge",
              "amount": 40000,
              "amount_refunded": 40000,
              "application": null,
              "application_fee": null,
              "application_fee_amount": null,
              "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
              "billing_details": {
                "address": {
                  "city": null,
                  "country": "FR",
                  "line1": null,
                  "line2": null,
                  "postal_code": null,
                  "state": null
                },
                "email": "xxxxxxxxx@outlook.fr",
                "name": "Jane Doe",
                "phone": null
              },
              "captured": true,
              "created": 1563594672,
              "currency": "eur",
              "customer": "cus_XXXXXXXXXXXXXX",
              "description": null,
              "destination": null,
              "dispute": null,
              "failure_code": null,
              "failure_message": null,
              "fraud_details": {
              },
              "invoice": null,
              "livemode": false,
              "metadata": {
                "payin_id": "%(payin_id)s"
              },
              "on_behalf_of": null,
              "order": null,
              "outcome": {
                "network_status": "approved_by_network",
                "reason": null,
                "risk_level": "not_assessed",
                "seller_message": "Payment complete.",
                "type": "authorized"
              },
              "paid": true,
              "payment_intent": null,
              "payment_method": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
              "payment_method_details": {
                "sepa_debit": {
                  "bank_code": "12345",
                  "branch_code": "10000",
                  "country": "FR",
                  "fingerprint": "XXXXXXXXXXXXXXXX",
                  "last4": "0000"
                },
                "type": "sepa_debit"
              },
              "receipt_email": null,
              "receipt_number": null,
              "receipt_url": "https://pay.stripe.com/receipts/...",
              "refunded": true,
              "refunds": {
                "object": "list",
                "data": [],
                "has_more": false,
                "total_count": 0,
                "url": "/v1/charges/py_XXXXXXXXXXXXXXXXXXXXXXXX/refunds"
              },
              "review": null,
              "shipping": null,
              "source": {
                "id": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
                "object": "source",
                "amount": null,
                "client_secret": "src_client_secret_XXXXXXXXXXXXXXXXXXXXXXXX",
                "created": 1563594673,
                "currency": "eur",
                "customer": "cus_XXXXXXXXXXXXXX",
                "flow": "none",
                "livemode": false,
                "mandate": {
                  "acceptance": {
                    "date": null,
                    "ip": null,
                    "offline": null,
                    "online": null,
                    "status": "pending",
                    "type": null,
                    "user_agent": null
                  },
                  "amount": null,
                  "currency": null,
                  "interval": "variable",
                  "notification_method": "none",
                  "reference": "XXXXXXXXXXXXXXXX",
                  "url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
                },
                "metadata": {
                },
                "owner": {
                  "address": {
                    "city": null,
                    "country": "FR",
                    "line1": null,
                    "line2": null,
                    "postal_code": null,
                    "state": null
                  },
                  "email": "xxxxxxxxx@outlook.fr",
                  "name": "Jane Doe",
                  "phone": null,
                  "verified_address": null,
                  "verified_email": null,
                  "verified_name": null,
                  "verified_phone": null
                },
                "sepa_debit": {
                  "last4": "0000",
                  "bank_code": "12345",
                  "branch_code": "10000",
                  "fingerprint": "XXXXXXXXXXXXXXXX",
                  "country": "FR",
                  "mandate_reference": "XXXXXXXXXXXXXXXX",
                  "mandate_url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
                },
                "statement_descriptor": null,
                "status": "chargeable",
                "type": "sepa_debit",
                "usage": "reusable"
              },
              "source_transfer": null,
              "statement_descriptor": "Liberapay %(payin_id)s",
              "status": "succeeded",
              "transfer": null,
              "transfer_group": "group_py_XXXXXXXXXXXXXXXXXXXXXXXX"
            }''' % params),
            stripe.api_key
        )
        bt_retrieve.return_value = stripe.BalanceTransaction.construct_from(
            json.loads('''{
              "amount": 40000,
              "available_on": 1564617600,
              "created": 1564038239,
              "currency": "eur",
              "description": null,
              "exchange_rate": null,
              "fee": 0,
              "fee_details": [],
              "id": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
              "net": 40000,
              "object": "balance_transaction",
              "source": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "status": "pending",
              "type": "payment"
            }'''),
            stripe.api_key
        )
        tr_retrieve.return_value = stripe.Transfer.construct_from(
            json.loads('''{
              "amount": 20000,
              "amount_reversed": 0,
              "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
              "created": 1564038240,
              "currency": "eur",
              "description": null,
              "destination": "acct_XXXXXXXXXXXXXXXX",
              "destination_payment": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "id": "tr_XXXXXXXXXXXXXXXXXXXXXXXX",
              "livemode": false,
              "metadata": {},
              "object": "transfer",
              "reversals": {
                "data": [],
                "has_more": false,
                "object": "list",
                "total_count": 0,
                "url": "/v1/transfers/tr_XXXXXXXXXXXXXXXXXXXXXXXX/reversals"
              },
              "reversed": false,
              "source_transaction": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
              "source_type": "card",
              "transfer_group": "group_py_XXXXXXXXXXXXXXXXXXXXXXXX"
            }''' % params),
            stripe.api_key
        )
        create_reversal.return_value = stripe.Reversal.construct_from(
            json.loads('''{
              "id": "trr_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "transfer_reversal",
              "amount": 20000,
              "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXZ",
              "created": %(recent_timestamp)s,
              "currency": "eur",
              "destination_payment_refund": null,
              "metadata": {
                  "payin_transfer_id": %(payin_transfer_id)s
              },
              "source_refund": null,
              "transfer": "tr_XXXXXXXXXXXXXXXXXXXXXXXX"
            }''' % params),
            stripe.api_key
        )
        chargeable_source = stripe.Source.construct_from(
            json.loads('''{
              "id": "src_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "source",
              "amount": null,
              "created": 1563594673,
              "currency": "eur",
              "customer": "cus_XXXXXXXXXXXXXX",
              "flow": "none",
              "livemode": false,
              "owner": {
                "address": {
                  "city": null,
                  "country": "FR",
                  "line1": null,
                  "line2": null,
                  "postal_code": null,
                  "state": null
                },
                "email": "xxxxxxxxx@outlook.fr",
                "name": "Jane Doe",
                "phone": null,
                "verified_address": null,
                "verified_email": null,
                "verified_name": null,
                "verified_phone": null
              },
              "sepa_debit": {
                "last4": "0000",
                "bank_code": "12345",
                "branch_code": "10000",
                "fingerprint": "XXXXXXXXXXXXXXXX",
                "country": "FR",
                "mandate_reference": "XXXXXXXXXXXXXXXX",
                "mandate_url": "https://hooks.stripe.com/adapter/sepa_debit/file/..."
              },
              "statement_descriptor": null,
              "status": "consumed",
              "type": "sepa_debit",
              "usage": "reusable"
            }'''),
            stripe.api_key
        )
        source_retrieve.return_value = chargeable_source
        consumed_source = stripe.Source.construct_from(
            dict(chargeable_source, status='consumed'),
            stripe.api_key
        )
        source_detach.return_value = consumed_source
        r = self.client.POST('/callbacks/stripe', {}, HTTP_STRIPE_SIGNATURE='fake')
        assert r.code == 200
        assert r.text == 'OK'
        payin = self.db.one("SELECT * FROM payins WHERE id = %s", (payin.id,))
        assert payin.status == 'succeeded'
        assert payin.refunded_amount == EUR('400.00')
        # Second event
        construct_event.return_value = stripe.Event.construct_from(
            json.loads('''{
              "id": "evt_XXXXXXXXXXXXXXXXXXXXXXXX",
              "object": "event",
              "api_version": "2018-05-21",
              "created": %(recent_timestamp)i,
              "data": {
                "object": {
                  "amount": 20000,
                  "amount_reversed": 20000,
                  "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "created": 1564038240,
                  "currency": "eur",
                  "description": null,
                  "destination": "acct_XXXXXXXXXXXXXXXX",
                  "destination_payment": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "id": "tr_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "livemode": false,
                  "metadata": {
                      "payin_transfer_id": %(payin_transfer_id)i
                  },
                  "object": "transfer",
                  "reversals": {
                    "data": [
                      {
                        "amount": 20000,
                        "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXZ",
                        "created": %(recent_timestamp)i,
                        "currency": "eur",
                        "destination_payment_refund": null,
                        "id": "trr_XXXXXXXXXXXXXXXXXXXXXXXX",
                        "metadata": {},
                        "object": "transfer_reversal",
                        "source_refund": null,
                        "transfer": "tr_XXXXXXXXXXXXXXXXXXXXXXXX"
                      }
                    ],
                    "has_more": false,
                    "object": "list",
                    "total_count": 1,
                    "url": "/v1/transfers/tr_XXXXXXXXXXXXXXXXXXXXXXXX/reversals"
                  },
                  "reversed": true,
                  "source_transaction": "py_XXXXXXXXXXXXXXXXXXXXXXXX",
                  "source_type": "card",
                  "transfer_group": "group_py_XXXXXXXXXXXXXXXXXXXXXXXX"
                }
              },
              "livemode": false,
              "type": "transfer.reversed"
            }''' % params),
            stripe.api_key
        )
        r = self.client.PxST('/callbacks/stripe', {}, HTTP_STRIPE_SIGNATURE='fake')
        assert r.code == 409
        assert r.text == 'This callback is too early.'
        self.db.run("UPDATE payin_transfers SET ctime = ctime - interval '1 hour'")
        r = self.client.POST('/callbacks/stripe', {}, HTTP_STRIPE_SIGNATURE='fake')
        assert r.code == 200
        assert r.text == 'OK'
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        for pt in payin_transfers:
            assert pt.status == 'succeeded'
            assert pt.reversed_amount == EUR('200.00')
        reversal = self.db.one("SELECT * FROM payin_transfer_reversals")
        assert reversal.remote_id == 'trr_XXXXXXXXXXXXXXXXXXXXXXXX'
        assert reversal.payin_refund is None
        assert reversal.amount == EUR('200.00')
        tip1 = alice.get_tip_to(bob)
        tip2 = alice.get_tip_to(LiberapayOrg)
        assert tip1.paid_in_advance == 0
        assert tip2.paid_in_advance == 0
        # Check that the notification was sent
        emails = self.get_emails()
        assert len(emails) == 1
        assert emails[0]['subject'] == "Your payment of €400.00 has been disputed"
        # Check that the receipt for this payment has been voided
        source_retrieve.return_value = consumed_source
        r = self.client.GET('/alice/receipts/direct/%i' % payin.id, auth_as=alice)
        assert r.code == 200
        assert ' fully refunded ' in r.text
