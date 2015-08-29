from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.testing.mangopay import MangopayHarness
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant


class TestRoutes(MangopayHarness):

    def hit(self, username, action, network, address, expected=200):
        auth_as = getattr(self, username)
        r =  self.client.POST('/%s/routes/%s.json' % (username, action),
                              data=dict(network=network, address=address),
                              auth_as=auth_as, raise_immediately=False)
        assert r.code == expected
        return r

    def test_delete_card(self):
        self.hit('janet', 'delete', 'mango-cc', self.card_id)

        janet = Participant.from_username('janet')
        assert janet.get_credit_card_error() == 'invalidated'
        assert janet.mangopay_user_id

    def test_delete_bank_account(self):
        self.hit('homer', 'delete', 'mango-ba', self.bank_account.Id)

        homer = Participant.from_username('homer')
        route = ExchangeRoute.from_address(homer, 'mango-ba', self.bank_account.Id)
        assert route.error == homer.get_bank_account_error() == 'invalidated'
        assert homer.mangopay_user_id

        # Check that update_error doesn't update an invalidated route
        route.update_error('some error')
        assert route.error == homer.get_bank_account_error() == 'invalidated'
