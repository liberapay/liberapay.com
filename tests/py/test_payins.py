from __future__ import absolute_import, division, print_function, unicode_literals

from liberapay.exceptions import MissingPaymentAccount
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.payin.common import (
    prepare_payin, update_payin,
    resolve_destination,
    prepare_payin_transfer, update_payin_transfer,
)
from liberapay.testing import Harness, EUR


class TestPayins(Harness):

    def make_payin_and_transfer(
        self, route, tippee, amount, provider,
        status='succeeded', error=None, payer_country=None,
        unit_amount=None, period=None
    ):
        payer = route.participant
        payin = prepare_payin(self.db, payer, amount, route)
        payin = update_payin(self.db, payin.id, 'fake', status, error)
        destination = resolve_destination(
            self.db, tippee, provider, payer, payer_country, amount
        )
        recipient = Participant.from_id(destination.participant)
        if tippee.kind == 'group':
            context = 'team-donation'
            team = tippee
        else:
            context = 'personal-donation'
            team = None
        pt = prepare_payin_transfer(
            self.db, payin, recipient, destination, context, amount,
            unit_amount, period, team.id
        )
        pt = update_payin_transfer(self.db, pt.id, 'fake', status, error)
        return payin, pt

    def add_payment_account(self, participant, provider, country='FR', **data):
        data.setdefault('id', 'x')
        data.setdefault('default_currency', None)
        data.setdefault('charges_enabled', None)
        data.setdefault('verified', True)
        data.setdefault('display_name', None)
        data.setdefault('token', None)
        data.update(p_id=participant.id, provider=provider, country=country)
        return self.db.one("""
            INSERT INTO payment_accounts
                        (participant, provider, country, id,
                         default_currency, charges_enabled, verified,
                         display_name, token)
                 VALUES (%(p_id)s, %(provider)s, %(country)s, %(id)s,
                         %(default_currency)s, %(charges_enabled)s, %(verified)s,
                         %(display_name)s, %(token)s)
              RETURNING *
        """, data)

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
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('2'), 'stripe')
        assert pt.destination == stripe_account_carl.pk
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('1'), 'stripe')
        assert pt.destination == stripe_account_bob.pk
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('4'), 'stripe')
        assert pt.destination == stripe_account_carl.pk
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('10'), 'stripe')
        assert pt.destination == stripe_account_carl.pk
        payin, pt = self.make_payin_and_transfer(alice_card, team, EUR('2'), 'stripe')
        assert pt.destination == stripe_account_bob.pk
