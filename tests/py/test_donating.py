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
        assert creator.recipient_settings.patron_visibilities is None
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
        creator = self.make_participant('creator', accepted_currencies=None)
        creator.update_recipient_settings(patron_visibilities=7)
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

        r = self.client.PxST(
            '/creator/tip.json',
            {
                'currency': 'USD',
                'selected_amount': 'custom',
                'period': 'monthly',
                'amount': '1111',
                'renewal_mode': '1',
            },
            auth_as=donor,
        )
        assert r.code == 400
        assert r.__class__.__name__ == 'BadAmount'

        r = self.client.POST(
            '/creator/tip',
            {
                'currency': 'USD',
                'selected_amount': 'custom',
                'period': 'monthly',
                'amount': '1111',
                'renewal_mode': '1',
                'visibility': '3',
            },
            auth_as=donor,
        )
        assert r.code == 400
        assert '$1,111.00' in r.text
        assert 'not a valid monthly donation amount' in r.text
        currency_values = {
            i.attrib['value'] for i in r.html_tree.findall(".//{*}input[@name='currency']")
        }
        assert currency_values == {'USD'}
        assert ' name="period" value="monthly" checked' in r.text
        assert ' value="1,111.00"' in r.text
        checked_renewal_modes = [
            i.attrib['value'] for i in r.html_tree.findall(".//{*}input[@name='renewal_mode']")
            if 'checked' in i.attrib
        ]
        assert checked_renewal_modes == ['1']
        checked_visibilities = [
            i.attrib['value'] for i in r.html_tree.findall(".//{*}input[@name='visibility']")
            if 'checked' in i.attrib
        ]
        assert checked_visibilities == ['3']

    def test_donation_form_v2_rejects_custom_amounts_in_unsupported_currency(self):
        self.make_participant('creator', accepted_currencies='USD')
        donor = self.make_participant('donor')

        r = self.client.PxST(
            '/creator/tip',
            {
                'currency': 'KRW',
                'selected_amount': 'custom',
                'period': 'monthly',
                'amount': '1111111',
                'renewal_mode': '1',
            },
            auth_as=donor,
        )

        assert r.code == 400
        assert r.__class__.__name__ == 'BadAmount'

    def test_donation_form_v2_preserves_hidden_visibility_on_error(self):
        creator = self.make_participant('creator', accepted_currencies=None)
        creator.update_recipient_settings(patron_visibilities=2)
        donor = self.make_participant('donor')

        r = self.client.POST(
            '/creator/tip',
            {
                'currency': 'USD',
                'selected_amount': 'custom',
                'period': 'monthly',
                'amount': '1111',
                'renewal_mode': '1',
                'visibility': '3',
            },
            auth_as=donor,
        )

        assert r.code == 400
        hidden_visibilities = [
            i.attrib['value'] for i in r.html_tree.findall(".//{*}input[@name='visibility']")
            if i.attrib['type'] == 'hidden'
        ]
        assert hidden_visibilities == ['2']

    def test_donation_form_v2_preserves_custom_amount_over_standard_tip_on_error(self):
        creator = self.make_participant('creator', accepted_currencies=None)
        creator.update_recipient_settings(patron_visibilities=7)
        donor = self.make_participant('donor')
        donor.set_tip_to(creator, USD('1.00'), renewal_mode=1, visibility=2)

        r = self.client.POST(
            '/creator/tip',
            {
                'currency': 'USD',
                'selected_amount': 'custom',
                'period': 'monthly',
                'amount': '1111',
                'renewal_mode': '2',
                'visibility': '3',
            },
            auth_as=donor,
        )

        assert r.code == 400
        checked_amounts = [
            i.attrib['value'] for i in r.html_tree.findall(".//{*}input[@name='selected_amount']")
            if 'checked' in i.attrib
        ]
        assert checked_amounts == ['custom']
        checked_renewal_modes = [
            i.attrib['value'] for i in r.html_tree.findall(".//{*}input[@name='renewal_mode']")
            if 'checked' in i.attrib
        ]
        assert checked_renewal_modes == ['2']
        checked_visibilities = [
            i.attrib['value'] for i in r.html_tree.findall(".//{*}input[@name='visibility']")
            if 'checked' in i.attrib
        ]
        assert checked_visibilities == ['3']
