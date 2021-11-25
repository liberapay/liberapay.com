from liberapay.testing import Harness, USD


class TestDonating(Harness):

    def test_donation_form_v2(self):
        creator = self.make_participant('creator', accepted_currencies=None)
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
