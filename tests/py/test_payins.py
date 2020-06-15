from decimal import Decimal
import json
from unittest.mock import patch

from markupsafe import Markup
from pando.utils import utcnow
import stripe

from liberapay.billing.payday import Payday
from liberapay.constants import DONATION_LIMITS, EPOCH, PAYIN_AMOUNTS, STANDARD_TIPS
from liberapay.exceptions import MissingPaymentAccount, NoSelfTipping
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.payin.common import resolve_amounts, resolve_team_donation
from liberapay.payin.paypal import sync_all_pending_payments
from liberapay.payin.prospect import PayinProspect
from liberapay.payin.stripe import settle_charge_and_transfers
from liberapay.testing import Harness, EUR, KRW, JPY, USD


class TestResolveAmounts(Harness):

    def test_resolve_low_amounts(self):
        naive_amounts = {1: EUR('20.00'), 2: EUR('0.01')}
        expected_amounts = {1: EUR('6.00'), 2: EUR('0.01')}
        resolved_amounts = resolve_amounts(EUR('6.01'), naive_amounts)
        assert resolved_amounts == expected_amounts


class TestResolveTeamDonation(Harness):

    def resolve(self, team, provider, payer, payer_country, payment_amount):
        tip = self.db.one("""
            SELECT *
              FROM current_tips
             WHERE tipper = %s
               AND tippee = %s
        """, (payer.id, team.id))
        donations = resolve_team_donation(
            self.db, team, provider, payer, payer_country, payment_amount, tip.amount
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
        team = self.make_participant('team', kind='group')
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
        account = self.resolve(team, 'stripe', alice, 'BE', EUR('42'))
        assert account == stripe_account_bob

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
            alice_card, team, EUR('6.90'), fee=EUR('0.60')
        )
        assert len(payin_transfers) == 2
        assert payin_transfers[0].amount == EUR('5.43')
        assert payin_transfers[0].destination == stripe_account_bob.pk
        assert payin_transfers[0].unit_amount == EUR('0.82')
        assert payin_transfers[0].n_units == 6
        assert payin_transfers[1].amount == EUR('0.87')
        assert payin_transfers[1].destination == stripe_account_carl.pk
        assert payin_transfers[1].unit_amount == EUR('0.19')
        assert payin_transfers[1].n_units == 6
        # Check that this donation has balanced the takes.
        takes = {t.member: t for t in self.db.all("""
            SELECT member, amount, paid_in_advance
              FROM current_takes
             WHERE team = %s
        """, (team.id,))}
        weeks_of_advance_bob = takes[bob.id].paid_in_advance / takes[bob.id].amount
        weeks_of_advance_carl = takes[carl.id].paid_in_advance / takes[carl.id].amount
        assert abs(weeks_of_advance_bob - weeks_of_advance_carl) <= Decimal('0.001')

        # Test after two paydays, when takes are quite higher than incomes
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


class TestPayinAmountSuggestions(Harness):

    def setUp(self):
        self.alice = self.make_participant('alice')
        self.bob = self.make_participant('bob', accepted_currencies=None)
        self.carl = self.make_participant('carl', accepted_currencies=None)
        self.dana = self.make_participant('dana', accepted_currencies=None)

    def test_minimum_weekly_EUR_tip(self):
        tip_amount = DONATION_LIMITS['EUR']['weekly'][0]
        tip = self.alice.set_tip_to(self.bob, tip_amount)
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == tip_amount
        assert pp.one_months_worth == tip_amount * 4
        assert pp.one_years_worth == tip_amount * 52
        assert pp.twelve_years_worth == pp.one_years_worth * 12
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [pp.min_acceptable_amount, pp.twelve_years_worth]

    def test_minimum_monthly_EUR_tip(self):
        tip_amount = DONATION_LIMITS['EUR']['monthly'][0]
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == DONATION_LIMITS['EUR']['weekly'][0]
        assert pp.one_months_worth == tip_amount
        assert pp.one_years_worth == tip_amount * 12
        assert pp.twelve_years_worth == pp.one_years_worth * 12
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [pp.min_acceptable_amount, pp.twelve_years_worth]

    def test_minimum_yearly_EUR_tip(self):
        tip_amount = DONATION_LIMITS['EUR']['yearly'][0]
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == DONATION_LIMITS['EUR']['weekly'][0]
        assert pp.one_months_worth == (tip_amount / 12).round()
        assert pp.one_years_worth == tip_amount
        assert pp.twelve_years_worth == pp.one_years_worth * 12
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [pp.min_acceptable_amount, pp.twelve_years_worth]

    def test_small_weekly_USD_tip(self):
        tip_amount = STANDARD_TIPS['USD'][1].weekly
        tip = self.alice.set_tip_to(self.bob, tip_amount)
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'USD'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == tip_amount
        assert pp.one_months_worth == tip_amount * 4
        assert pp.one_years_worth == tip_amount * 52
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['USD']
        assert pp.suggested_amounts == [USD('2.00'), USD('12.00')]

    def test_small_monthly_USD_tip(self):
        tip_amount = USD('1.00')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'USD'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == USD('0.23')
        assert pp.one_months_worth == tip_amount
        assert pp.one_years_worth == tip_amount * 12
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['USD']
        assert pp.suggested_amounts == [USD('2.00'), USD('12.00')]

    def test_small_yearly_USD_tip(self):
        tip_amount = USD('10.00')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'USD'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == USD('0.19')
        assert pp.one_months_worth == USD('0.83')
        assert pp.one_years_worth == tip_amount
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['USD']
        assert pp.suggested_amounts == [USD('10.00'), USD('12.00')]

    def test_medium_weekly_JPY_tip(self):
        tip_amount = STANDARD_TIPS['JPY'][2].weekly
        tip = self.alice.set_tip_to(self.bob, tip_amount)
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'JPY'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == tip_amount
        assert pp.one_months_worth == tip_amount * 4
        assert pp.one_years_worth == tip_amount * 52
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['JPY']
        assert pp.suggested_amounts == [JPY('520'), JPY('1000'), JPY('6760')]

    def test_medium_monthly_JPY_tip(self):
        tip_amount = JPY('500')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'JPY'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == JPY('115')
        assert pp.one_months_worth == tip_amount
        assert pp.one_years_worth == tip_amount * 12
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['JPY']
        assert pp.suggested_amounts == [JPY('500'), JPY('1000'), JPY('6000')]

    def test_medium_yearly_JPY_tip(self):
        tip_amount = JPY('5000')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'JPY'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == JPY('96')
        assert pp.one_months_worth == JPY('417')
        assert pp.one_years_worth == tip_amount
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['JPY']
        assert pp.suggested_amounts == [JPY('5000')]

    def test_large_weekly_EUR_tip(self):
        tip_amount = STANDARD_TIPS['EUR'][3].weekly
        tip = self.alice.set_tip_to(self.bob, tip_amount)
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == tip_amount
        assert pp.one_months_worth == tip_amount * 4
        assert pp.one_years_worth == tip_amount * 52
        assert pp.suggested_amounts == [
            EUR('20.00'), EUR('65.00'), EUR('130.00'), EUR('260.00')
        ]

    def test_large_monthly_EUR_tip(self):
        tip_amount = EUR('25.00')
        tip = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        pp = PayinProspect([tip], 'stripe')
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
        pp = PayinProspect([tip], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount
        assert pp.one_weeks_worth == EUR('9.61')
        assert pp.one_months_worth == EUR('41.67')
        assert pp.one_years_worth == tip_amount
        assert pp.suggested_amounts == [EUR('500.00')]

    def test_two_small_monthly_USD_tips(self):
        tip_amount = USD('1.00')
        tip1 = self.alice.set_tip_to(self.bob, tip_amount, period='monthly')
        tip2 = self.alice.set_tip_to(self.carl, tip_amount, period='monthly')
        pp = PayinProspect([tip1, tip2], 'stripe')
        assert pp.currency == 'USD'
        assert pp.period == 'monthly'
        assert pp.one_periods_worth == tip_amount * 2
        assert pp.one_weeks_worth == USD('0.46')
        assert pp.one_months_worth == pp.one_periods_worth
        assert pp.one_years_worth == tip_amount * 24
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['USD']
        assert pp.suggested_amounts == [USD('2.00'), USD('12.00')]

    def test_two_medium_yearly_KRW_tips(self):
        tip_amount = KRW('50000')
        tip1 = self.alice.set_tip_to(self.bob, tip_amount, period='yearly')
        tip2 = self.alice.set_tip_to(self.carl, tip_amount, period='yearly')
        pp = PayinProspect([tip1, tip2], 'stripe')
        assert pp.currency == 'KRW'
        assert pp.period == 'yearly'
        assert pp.one_periods_worth == tip_amount * 2
        assert pp.one_weeks_worth == KRW('1922')
        assert pp.one_months_worth == KRW('8333')
        assert pp.one_years_worth == pp.one_periods_worth
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['KRW']
        assert pp.suggested_amounts == [KRW('100000')]

    def test_two_very_different_EUR_tips(self):
        tip1 = self.alice.set_tip_to(self.bob, EUR('0.24'), period='weekly')
        tip2 = self.alice.set_tip_to(self.carl, EUR('240.00'), period='yearly')
        pp = PayinProspect([tip1, tip2], 'stripe')
        assert pp.currency == 'EUR'
        assert pp.period == 'weekly'
        assert pp.one_periods_worth == EUR('4.86')
        assert pp.one_weeks_worth == pp.one_weeks_worth
        assert pp.one_months_worth == pp.one_weeks_worth * 4
        assert pp.one_years_worth == EUR('252.48')
        assert pp.low_fee_amount == PAYIN_AMOUNTS['stripe']['low_fee']['EUR']
        assert pp.suggested_amounts == [
            EUR('19.40'), EUR('63.12'), EUR('126.24'), EUR('252.48')
        ]

    def test_three_very_different_EUR_tips(self):
        tip1 = self.alice.set_tip_to(self.bob, EUR('0.01'), period='weekly')
        tip2 = self.alice.set_tip_to(self.carl, EUR('1.00'), period='monthly')
        tip3 = self.alice.set_tip_to(self.dana, EUR('5200.00'), period='yearly')
        pp = PayinProspect([tip1, tip2, tip3], 'stripe')
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
        r = self.client.GxT('/donor/giving/pay/paypal/1', auth_as=self.donor)
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
        cls.sepa_direct_debit_token = stripe.Token.create(bank_account=dict(
            country='DE',
            currency='EUR',
            account_number='DE89370400440532013000',
            account_holder_name='Jane Doe',
        ))
        acct_ch_token = stripe.Token.create(account=dict(
            tos_shown_and_accepted=True,
        ))
        cls.acct_switzerland = stripe.Account.create(
            account_token=acct_ch_token.id,
            country='CH',
            type='custom',
        )
        cls.offset = 1400

    def setUp(self):
        super().setUp()
        self.__class__.offset += 10
        self.db.run("ALTER SEQUENCE participants_id_seq RESTART WITH %s", (self.offset,))
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

    def test_00_payin_stripe_card(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH %s", (self.offset,))
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH %s", (self.offset,))
        self.add_payment_account(self.creator_1, 'stripe')
        tip = self.donor.set_tip_to(self.creator_1, EUR('0.02'))

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
        assert payin.status == 'succeeded'
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
        assert payin.status == 'succeeded'
        assert payin.amount_settled.currency == 'EUR'
        assert payin.fee.currency == 'EUR'
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
        assert payin.status == 'pending'
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
        assert pt1.amount == EUR('49.48')
        assert pt1.remote_id is not None
        assert pt2.status == 'succeeded'
        assert pt2.amount == EUR('49.47')
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


class TestRefundsStripe(Harness):

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
    @patch('stripe.Transfer.retrieve')
    @patch('stripe.Webhook.construct_event')
    def test_refunded_destination_charge(
        self, construct_event, tr_retrieve, source_retrieve, bt_retrieve
    ):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        route = self.upsert_route(alice, 'stripe-card')
        alice.set_tip_to(bob, EUR('2.46'))
        payin, pt = self.make_payin_and_transfer(
            route, bob, EUR(400), fee=EUR('3.45'),
            remote_id='py_XXXXXXXXXXXXXXXXXXXXXXXX',
            pt_remote_id='tr_XXXXXXXXXXXXXXXXXXXXXXXX',
        )
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
        # Check that a notification was sent
        notifs = alice.get_notifs()
        assert len(notifs) == 1
        assert notifs[0].event == 'payin_refund_initiated'
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
    @patch('stripe.Transfer.retrieve')
    @patch('stripe.Webhook.construct_event')
    def test_refunded_split_charge(
        self, construct_event, tr_retrieve, source_retrieve, bt_retrieve
    ):
        alice = self.make_participant('alice')
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
        tr_retrieve.return_value = stripe.Transfer.construct_from(
            json.loads('''{
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
              "metadata": {},
              "object": "transfer",
              "reversals": {
                "data": [
                  {
                    "amount": 20000,
                    "balance_transaction": "txn_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "created": %(recent_timestamp)i,
                    "currency": "eur",
                    "destination_payment_refund": "pyr_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "id": "trr_XXXXXXXXXXXXXXXXXXXXXXXX",
                    "metadata": {},
                    "object": "transfer_reversal",
                    "source_refund": "pyr_XXXXXXXXXXXXXXXXXXXXXXXX",
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
            }''' % params),
            stripe.api_key
        )
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
        # Check that a notification was sent
        notifs = alice.get_notifs()
        assert len(notifs) == 1
        assert notifs[0].event == 'payin_refund_initiated'
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
    @patch('stripe.Transfer.retrieve')
    @patch('stripe.Webhook.construct_event')
    def test_charge_dispute(
        self, construct_event, tr_retrieve, create_reversal, source_retrieve,
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
        # Check that no notification was sent
        notifs = alice.get_notifs()
        assert len(notifs) == 0
        # Check that the receipt for this payment has been voided
        source_retrieve.return_value = consumed_source
        r = self.client.GET('/alice/receipts/direct/%i' % payin.id, auth_as=alice)
        assert r.code == 200
        assert ' fully refunded ' in r.text
