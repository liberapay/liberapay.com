from liberapay.testing import Harness, USD


class TestDonating(Harness):

    def test_donation_form_v2(self):
        creator = self.make_participant(
            'creator', accepted_currencies=None, email='creator@liberapay.com',
        )
        creator.update_recipient_settings(patron_visibilities=7)
        r = self.client.GET('/creator/donate?currency=KRW')
        assert r.code == 200
        assert ">Pledge<" in r.text
        assert ' name="currency" value="KRW"' in r.text, r.text
        self.add_payment_account(creator, 'stripe')
        r = self.client.GET('/creator/donate?currency=JPY&amount=2000&period=monthly')
        assert r.code == 200
        assert ">Donate<" in r.text
        assert ' value="2,000"'
        assert ' name="period" value="monthly" checked'
        donor = self.make_participant('donor')
        r = self.client.PxST(
            '/creator/tip',
            {
                'currency': 'USD',
                'selected_amount': '1.00',
                'renewal_mode': '2',
                'visibility': '3',
            },
            auth_as=donor,
        )
        assert r.code == 302
        assert r.headers[b'Location'] == (b'/donor/giving/pay/?beneficiary=%i' % creator.id)
        tip = donor.get_tip_to(creator)
        assert tip.amount == USD('1.00')
        assert tip.renewal_mode == 2
        assert tip.visibility == 3

    def test_donation_form_v2_for_paypal_only_recipient(self):
        creator = self.make_participant(
            'creator', accepted_currencies=None, email='creator@liberapay.com',
        )
        self.add_payment_account(creator, 'paypal')
        assert creator.payment_providers == 2
        assert creator.recipient_settings.patron_visibilities == 0
        r = self.client.GET('/creator/donate')
        assert r.code == 200
        assert "This donation won&#39;t be secret, " in r.text, r.text
        creator.update_recipient_settings(patron_visibilities=7)
        assert creator.recipient_settings.patron_visibilities == 7
        r = self.client.GET('/creator/donate')
        assert r.code == 200

    def test_donation_form_v2_does_not_overwrite_visibility(self):
        creator = self.make_participant(
            'creator', accepted_currencies=None, email='creator@liberapay.com',
        )
        creator.update_recipient_settings(patron_visibilities=7)
        self.add_payment_account(creator, 'stripe')
        donor = self.make_participant('donor')
        donor.set_tip_to(creator, USD('10.00'), renewal_mode=1, visibility=3)
        r = self.client.PxST(
            '/creator/tip',
            {
                'currency': 'USD',
                'selected_amount': '1.00',
                'renewal_mode': '2',
            },
            auth_as=donor,
        )
        assert r.code == 302
        assert r.headers[b'Location'].startswith(b'/donor/giving/')
        tip = donor.get_tip_to(creator)
        assert tip.amount == USD('1.00')
        assert tip.renewal_mode == 2
        assert tip.visibility == 3

    def test_donation_form_v2_enforces_amount_limits(self):
        self.make_participant('creator', accepted_currencies=None)
        donor = self.make_participant('donor')
        r = self.client.PxST(
            '/creator/tip',
            {'currency': 'GBP', 'selected_amount': '-inf'},
            auth_as=donor,
        )
        assert r.code == 400
        assert r.__class__.__name__ == 'InvalidNumber'
        r = self.client.PxST(
            '/creator/tip',
            {'currency': 'JPY', 'selected_amount': '0.1'},
            auth_as=donor,
        )
        assert r.code == 400
        assert r.__class__.__name__ == 'BadAmount'
        r = self.client.PxST(
            '/creator/tip',
            {'currency': 'EUR', 'selected_amount': '0.001'},
            auth_as=donor,
        )
        assert r.code == 400
        assert r.__class__.__name__ == 'BadAmount'
        r = self.client.PxST(
            '/creator/tip',
            {'currency': 'USD', 'selected_amount': '100.01'},
            auth_as=donor,
        )
        assert r.code == 400
        assert r.__class__.__name__ == 'BadAmount'
        r = self.client.PxST(
            '/creator/tip',
            {'currency': 'CHF', 'selected_amount': 'inf'},
            auth_as=donor,
        )
        assert r.code == 400
        assert r.__class__.__name__ == 'InvalidNumber'
