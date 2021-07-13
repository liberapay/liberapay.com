from liberapay.testing import Harness


user_data = {
    'name': 'Kàthryn Janeway',
    'postal_address.country': 'US',
    'nationality': 'IS',
    'dirthdate': '1995-01-16',
}


class TestIdentity(Harness):

    def test_identity_form_v2(self):
        janeway = self.make_participant('janeway', email='janeway@example.org')

        # Test getting the form
        r = self.client.GET('/janeway/identity', auth_as=janeway)
        assert r.code == 200

        # Test posting nothing
        r = self.client.PxST('/janeway/identity', {}, auth_as=janeway)
        assert r.code == 302, r.text
        assert b'/janeway/identity' in r.headers[b'Location']

        # Test posting the data
        r = self.client.PxST('/janeway/identity', user_data, auth_as=janeway)
        assert r.code == 302, r.text
        assert b'/janeway/identity' in r.headers[b'Location']
