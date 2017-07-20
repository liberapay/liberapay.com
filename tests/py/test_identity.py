# coding: utf8

from __future__ import print_function, unicode_literals

from liberapay.testing import Harness


class TestIdentity(Harness):

    def test_identity_form(self):
        janeway = self.make_participant(
            'janeway', email='janeway@example.org', mangopay_user_id=None,
            mangopay_wallet_id=None,
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

        # Create a mangopay legal user
        self.db.run("UPDATE participants SET kind = 'organization'")
        self.db.run("UPDATE participants SET mangopay_user_id = mangopay_wallet_id = NULL")
        data = {'LegalRepresentative'+k: v for k, v in user_data.items()}
        data['LegalPersonType'] = 'BUSINESS'
        data['Name'] = 'Starfleet'
        data['terms'] = 'agree'
        r = self.client.POST('/janeway/identity', data, **kw)
        assert r.code == 200, r.text
        janeway = janeway.refetch()
        assert janeway.mangopay_user_id

        # Edit the legal user
        data2 = dict(data, LegalPersonType='ORGANIZATION')
        r = self.client.POST('/janeway/identity', data2, **kw)
        assert r.code == 200, r.text
        janeway2 = janeway.refetch()
        assert janeway2.mangopay_user_id == janeway.mangopay_user_id
