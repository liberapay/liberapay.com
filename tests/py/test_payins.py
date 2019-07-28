import json
from unittest.mock import patch

from markupsafe import Markup
from pando.utils import utcnow
import stripe

from liberapay.constants import EPOCH
from liberapay.exceptions import MissingPaymentAccount
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.payin.common import resolve_destination
from liberapay.payin.paypal import sync_all_pending_payments
from liberapay.testing import Harness, EUR, JPY, USD


class TestResolveDestination(Harness):

    def test_resolve_destination(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        team = self.make_participant('team', kind='group')
        alice.set_tip_to(team, EUR('10'))

        # Test without payment account
        team.add_member(bob)
        with self.assertRaises(MissingPaymentAccount):
            resolve_destination(self.db, team, 'stripe', alice, 'FR', EUR('10'))

        # Test without payment account at the requested provider
        stripe_account_bob = self.add_payment_account(bob, 'stripe')
        with self.assertRaises(MissingPaymentAccount):
            resolve_destination(self.db, team, 'paypal', alice, 'US', EUR('10'))

        # Test with a single member and the take at zero
        account = resolve_destination(self.db, team, 'stripe', alice, 'GB', EUR('7'))
        assert account == stripe_account_bob

        # Test with two members but only one payment account
        team.add_member(carl)
        account = resolve_destination(self.db, team, 'stripe', alice, 'CH', EUR('8'))
        assert account == stripe_account_bob

        # Test with two members but only one payment account at the requested provider
        paypal_account_carl = self.add_payment_account(carl, 'paypal')
        account = resolve_destination(self.db, team, 'stripe', alice, 'BE', EUR('42'))
        assert account == stripe_account_bob

        # Test with two members and both takes at zero
        stripe_account_carl = self.add_payment_account(carl, 'stripe')
        account = resolve_destination(self.db, team, 'stripe', alice, 'PL', EUR('5.46'))
        assert account == stripe_account_bob
        account = resolve_destination(self.db, team, 'paypal', alice, 'PL', EUR('99.9'))
        assert account == paypal_account_carl

        # Test with two members and one non-zero take
        team.set_take_for(bob, EUR('1'), bob)
        account = resolve_destination(self.db, team, 'stripe', alice, 'RU', EUR('50.02'))
        assert account == stripe_account_bob
        account = resolve_destination(self.db, team, 'paypal', alice, 'RU', EUR('33'))
        assert account == paypal_account_carl

        # Test with two members and two different non-zero takes
        team.set_take_for(carl, EUR('2'), carl)
        account = resolve_destination(self.db, team, 'stripe', alice, 'BR', EUR('10'))
        assert account == stripe_account_carl
        account = resolve_destination(self.db, team, 'stripe', alice, 'BR', EUR('1'))
        assert account == stripe_account_carl
        account = resolve_destination(self.db, team, 'paypal', alice, 'BR', EUR('5'))
        assert account == paypal_account_carl

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

    def test_00_payin_stripe_card(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH 100")
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH 100")
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
            'tips': str(tip['id']),
            'token': 'tok_visa',
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/100'
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('24.99')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('24.99')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/100', auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded'
        assert payin.amount_settled == EUR('24.99')
        assert payin.fee == EUR('0.97')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'succeeded'
        assert pt.amount == EUR('24.02')

    def test_02_payin_stripe_card_one_to_many(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH 102")
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH 102")
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
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/102'
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
        r = self.client.GET('/donor/giving/pay/stripe/102', auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded'
        assert payin.amount_settled == EUR('78.66')
        assert payin.fee == EUR('2.53')
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'succeeded'
        assert pt1.amount == EUR('38.07')
        assert pt1.remote_id
        assert pt2.status == 'succeeded'
        assert pt2.amount == EUR('38.06')

    def test_01_payin_stripe_sdd(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH 101")
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH 101")
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
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/101'
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('52.00')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('52.00')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/101', auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pending'
        assert payin.amount_settled is None
        assert payin.fee is None
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pending'
        assert pt.amount == EUR('52.00')

    def test_03_payin_stripe_sdd_one_to_many(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH 203")
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH 203")
        self.add_payment_account(self.creator_1, 'stripe', id=self.acct_switzerland.id)
        self.add_payment_account(self.creator_3, 'stripe')
        self.add_payment_account(self.creator_3, 'paypal')
        tip1 = self.donor.set_tip_to(self.creator_1, EUR('12.00'))
        tip3 = self.donor.set_tip_to(self.creator_3, EUR('12.00'))

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
        sepa_direct_debit_token = stripe.Token.create(bank_account=dict(
            country='FR',
            currency='EUR',
            account_number='FR1420041010050500013M02606',
            account_holder_name='Jane Doe',
        ))
        form_data = {
            'amount': '100.00',
            'currency': 'EUR',
            'tips': '%i,%i' % (tip1['id'], tip3['id']),
            'token': sepa_direct_debit_token.id,
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/203'
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
        r = self.client.GET('/donor/giving/pay/stripe/203', auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pending'
        assert payin.amount_settled is None
        assert payin.fee is None
        payin_transfers = self.db.all("SELECT * FROM payin_transfers ORDER BY id")
        assert len(payin_transfers) == 2
        pt1, pt2 = payin_transfers
        assert pt1.status == 'pre'
        assert pt1.amount == EUR('50.00')
        assert pt1.remote_id is None
        assert pt2.status == 'pre'
        assert pt2.amount == EUR('50.00')
        assert pt2.remote_id is None

    def test_04_payin_intent_stripe_card(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH 304")
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH 304")
        self.add_payment_account(self.creator_1, 'stripe')
        tip = self.donor.set_tip_to(self.creator_1, EUR('0.25'))

        # 1st request: test getting the payment page
        r = self.client.GET(
            '/donor/giving/pay/stripe?method=card&beneficiary=%i' % self.creator_1.id,
            auth_as=self.donor
        )
        assert r.code == 200, r.text

        # 2nd request: prepare the payment
        pm = stripe.PaymentMethod.create(type='card', card={'token': 'tok_visa'})
        form_data = {
            'amount': '25',
            'currency': 'EUR',
            'tips': str(tip['id']),
            'stripe_pm_id': pm.id,
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/304'
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'pre'
        assert payin.amount == EUR('25.00')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'pre'
        assert pt.amount == EUR('25.00')

        # 3rd request: execute the payment
        r = self.client.GET('/donor/giving/pay/stripe/304', auth_as=self.donor)
        assert r.code == 200, r.text
        payin = self.db.one("SELECT * FROM payins")
        assert payin.status == 'succeeded', payin
        assert payin.amount_settled == EUR('25.00')
        assert payin.fee == EUR('0.98')
        pt = self.db.one("SELECT * FROM payin_transfers")
        assert pt.status == 'succeeded'
        assert pt.amount == EUR('24.02')

    def test_05_payin_intent_stripe_card_one_to_many(self):
        self.db.run("ALTER SEQUENCE payins_id_seq RESTART WITH 105")
        self.db.run("ALTER SEQUENCE payin_transfers_id_seq RESTART WITH 105")
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
        pm = stripe.PaymentMethod.create(type='card', card={'token': 'tok_visa'})
        form_data = {
            'amount': '100.00',
            'currency': 'EUR',
            'tips': '%i,%i' % (tip1['id'], tip3['id']),
            'stripe_pm_id': pm.id,
        }
        r = self.client.PxST('/donor/giving/pay/stripe', form_data, auth_as=self.donor)
        assert r.code == 200, r.text
        assert r.headers[b'Refresh'] == b'0;url=/donor/giving/pay/stripe/105'
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
        r = self.client.GET('/donor/giving/pay/stripe/105', auth_as=self.donor)
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
    @patch('stripe.Transfer.retrieve')
    @patch('stripe.Webhook.construct_event')
    def test_refunded_destination_charge(self, construct_event, tr_retrieve, bt_retrieve):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        route = self.upsert_route(alice, 'stripe-card')
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
        notifs = alice.get_notifs()
        assert len(notifs) == 1
        assert notifs[0].event == 'payin_refund_initiated'

    @patch('stripe.BalanceTransaction.retrieve')
    @patch('stripe.Transfer.retrieve')
    @patch('stripe.Webhook.construct_event')
    def test_refunded_split_charge(self, construct_event, tr_retrieve, bt_retrieve):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe', id='acct_XXXXXXXXXXXXXXXX')
        LiberapayOrg = self.make_participant('LiberapayOrg')
        self.add_payment_account(LiberapayOrg, 'stripe', id='acct_1ChyayFk4eGpfLOC')
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
        notifs = alice.get_notifs()
        assert len(notifs) == 1
        assert notifs[0].event == 'payin_refund_initiated'
