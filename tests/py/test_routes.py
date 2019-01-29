from mangopay.resources import Card
from mock import patch

from liberapay.testing.mangopay import MangopayHarness
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant


class TestRoutes(MangopayHarness):

    def hit(self, username, action, network, address, expected=200):
        auth_as = getattr(self, username)
        r = self.client.POST('/%s/routes/%s.json' % (username, action),
                             data=dict(network=network, address=address),
                             auth_as=auth_as, raise_immediately=False)
        assert r.code == expected
        return r

    @patch('mangopay.resources.Card.get')
    def test_associate_nonexistent_card(self, Card_get):
        Card_get.side_effect = Card.DoesNotExist
        r = self.client.PxST('/homer/routes/credit-card.json',
                             data={'CardId': '-1'}, auth_as=self.homer)
        assert r.code == 400
        cards = ExchangeRoute.from_network(self.homer, 'mango-cc')
        assert not cards

    def test_delete_card(self):
        self.hit('janet', 'delete', 'mango-cc', self.card_id)

        janet = Participant.from_username('janet')
        cards = ExchangeRoute.from_network(janet, 'mango-cc')
        assert not cards
        assert janet.mangopay_user_id

    def test_delete_bank_account(self):
        self.hit('homer', 'delete', 'mango-ba', self.bank_account.Id)

        homer = Participant.from_username('homer')
        route = ExchangeRoute.from_address(homer, 'mango-ba', self.bank_account.Id)
        assert route.status == 'canceled'
        assert homer.mangopay_user_id
