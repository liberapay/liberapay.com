from markupsafe import Markup
import stripe

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
        assert payin.status == 'pending'

        # 4th request: execute the payment
        qs = '?paymentId=PAYID-LROG6RI5M728524H1063005Y&token=EC-9X899333Y0716272U&PayerID=6C9EQBCEQY4MA'
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
