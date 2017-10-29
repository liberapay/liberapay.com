# coding: utf8

from __future__ import print_function, unicode_literals

from decimal import Decimal as D

from liberapay.billing.transactions import charge, create_wallet
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.testing import Harness
from liberapay.testing.mangopay import create_card


class TestIdentity(Harness):

    def test_identity_form(self):
        janeway = self.make_participant(
            'janeway', email='janeway@example.org', mangopay_user_id=None,
        )
        assert janeway.mangopay_user_id is None

        # Create a mangopay natural user
        user_data = {
            'FirstName': 'Kàthryn',
            'LastName': 'Janeway',
            'CountryOfResidence': 'US',
            'Nationality': 'IS',
            'Birthday': '1995-01-16',
        }
        data = dict(user_data, terms='agree')
        kw = dict(auth_as=janeway, raise_immediately=False, xhr=True)
        r = self.client.POST('/janeway/identity', data, **kw)
        assert r.code == 200, r.text
        janeway = janeway.refetch()
        assert janeway.mangopay_user_id

        # Test the rendering of the identity page
        r = self.client.GET('/janeway/identity.html', auth_as=janeway)
        assert r.code == 200, r.text
        assert user_data['FirstName'] in r.text

        # Edit the natural user
        data2 = dict(data, FirstName='Kathryn', Nationality='US', Birthday='1970-01-01')
        r = self.client.POST('/janeway/identity', data2, **kw)
        assert r.code == 200, r.text
        janeway2 = janeway.refetch()
        assert janeway2.mangopay_user_id == janeway.mangopay_user_id

        # Add some money for the next test
        create_wallet(self.db, janeway, 'EUR')
        cr = create_card(janeway.mangopay_user_id)
        route = ExchangeRoute.insert(janeway, 'mango-cc', cr.CardId, currency='EUR')
        charge(self.db, route, D('20.00'), 'http://127.0.0.1/')

        # Switch to a legal user
        data = dict(data2)
        data['organization'] = 'yes'
        data['LegalPersonType'] = 'BUSINESS'
        data['Name'] = 'Starfleet'
        data['confirmed'] = 'yes'
        r = self.client.POST('/janeway/identity', data, **kw)
        assert r.code == 200, r.text
        janeway = janeway.refetch()
        assert janeway.mangopay_user_id != janeway2.mangopay_user_id
        assert janeway.kind == 'organization'
        self.db.self_check()

        # Edit the legal user
        data2 = dict(data, LegalPersonType='ORGANIZATION')
        r = self.client.POST('/janeway/identity', data2, **kw)
        assert r.code == 200, r.text
        janeway2 = janeway.refetch()
        assert janeway2.mangopay_user_id == janeway.mangopay_user_id
