from liberapay.testing import Harness, EUR, JPY, USD


class TestReceipts(Harness):

    def setUp(self):
        self.donor = self.make_participant('alice')
        self.donor.add_email('alice@liberapay.com')
        self.recipient = self.make_participant('bob', accepted_currencies=None)

    def test_paypal_receipt(self):
        self.donor.set_tip_to(self.recipient, EUR('1.00'))
        route = self.upsert_route(self.donor, 'paypal')
        payin = self.make_payin_and_transfer(route, self.recipient, EUR('20.00'))[0]
        r = self.client.GET(
            self.donor.path('receipts/direct/%s' % payin.id),
            auth_as=self.donor
        )
        assert r.code == 200, r.text

    def test_stripe_card_receipt(self):
        self.donor.set_tip_to(self.recipient, JPY('100'))
        route = self.upsert_route(
            self.donor, 'stripe-card', address='pm_1EZc8vFk4eGpfLOCibbhONPo',
            owner_name='Foo Bar',
        )
        payin = self.make_payin_and_transfer(route, self.recipient, JPY('2001'))[0]
        r = self.client.GET(
            self.donor.path('receipts/direct/%s' % payin.id),
            auth_as=self.donor
        )
        assert r.code == 200, r.text

    def test_stripe_direct_debit_receipt(self):
        self.donor.set_tip_to(self.recipient, USD('0.99'))
        route = self.upsert_route(
            self.donor, 'stripe-sdd', address='src_1E42IaFk4eGpfLOCUau5nIdg',
            owner_name='Foo Bar',
        )
        payin = self.make_payin_and_transfer(route, self.recipient, USD('20.02'))[0]
        r = self.client.GET(
            self.donor.path('receipts/direct/%s' % payin.id),
            auth_as=self.donor
        )
        assert r.code == 200, r.text
