from mangopay.resources import Card, Mandate
from postgres.orm import Model
import stripe

from ..exceptions import InvalidId


class ExchangeRoute(Model):

    typname = "exchange_routes"

    def __bool__(self):
        return self.status in ('pending', 'chargeable')

    __nonzero__ = __bool__

    @classmethod
    def from_id(cls, participant, id, _raise=True):
        route = cls.db.one("""
            SELECT r
              FROM exchange_routes r
             WHERE r.id = %(r_id)s
               AND r.participant = %(p_id)s
        """, dict(r_id=id, p_id=participant.id))
        if route is not None:
            route.__dict__['participant'] = participant
        elif _raise:
            raise InvalidId(id, cls.__name__)
        return route

    @classmethod
    def from_network(cls, participant, network, currency=None):
        participant_id = participant.id
        if network.startswith('mango-'):
            remote_user_id = participant.mangopay_user_id
        elif network.startswith('stripe-'):
            remote_user_id = None
        r = cls.db.all("""
            SELECT r
              FROM exchange_routes r
             WHERE participant = %(participant_id)s
               AND COALESCE(remote_user_id = %(remote_user_id)s, true)
               AND network::text = %(network)s
               AND status = 'chargeable'
               AND COALESCE(currency::text, '') = COALESCE(%(currency)s::text, '')
               AND (one_off IS FALSE OR ctime > (current_timestamp - interval '6 hours'))
          ORDER BY r.id DESC
        """, locals())
        for route in r:
            route.__dict__['participant'] = participant
        return r

    @classmethod
    def from_address(cls, participant, network, address):
        participant_id = participant.id
        r = cls.db.one("""
            SELECT r
              FROM exchange_routes r
             WHERE participant = %(participant_id)s
               AND network = %(network)s
               AND address = %(address)s
        """, locals())
        if r:
            r.__dict__['participant'] = participant
        return r

    @classmethod
    def insert(cls, participant, network, address, status,
               one_off=False, remote_user_id=None, country=None, currency=None):
        p_id = participant.id
        if network.startswith('mango-'):
            remote_user_id = participant.mangopay_user_id
        r = cls.db.one("""
            INSERT INTO exchange_routes AS r
                        (participant, network, address, status,
                         one_off, remote_user_id, country, currency)
                 VALUES (%(p_id)s, %(network)s, %(address)s, %(status)s,
                         %(one_off)s, %(remote_user_id)s, %(country)s, %(currency)s)
              RETURNING r
        """, locals())
        r.__dict__['participant'] = participant
        return r

    @classmethod
    def upsert_generic_route(cls, participant, network):
        if network.startswith('mango-'):
            remote_user_id = participant.mangopay_user_id
        elif network == 'paypal':
            remote_user_id = 'x'
        r = cls.db.one("""
            INSERT INTO exchange_routes AS r
                        (participant, network, address, one_off, status, remote_user_id)
                 VALUES (%s, %s, 'x', false, 'chargeable', %s)
            ON CONFLICT (participant, network, address) DO UPDATE
                    SET one_off = false  -- dummy update
              RETURNING r
        """, (participant.id, network, remote_user_id))
        r.__dict__['participant'] = participant
        return r

    def invalidate(self, obj=None):
        if self.network.startswith('stripe-'):
            if self.address.startswith('pm_'):
                stripe.PaymentMethod.detach(self.address)
            else:
                source = stripe.Source.retrieve(self.address).detach()
                assert source.status == 'consumed'
                self.update_status(source.status)
                return
        elif self.network == 'mango-cc':
            card = obj or Card.get(self.address)
            if card.Active:
                card.Active = False
                card.save()
                assert card.Active is False, card.Active
        if self.mandate:
            mandate = Mandate.get(self.mandate)
            if mandate.Status in ('SUBMITTED', 'ACTIVE'):
                mandate.cancel()
        self.update_status('canceled')

    def set_mandate(self, mandate_id):
        self.db.run("""
            UPDATE exchange_routes
               SET mandate = %s
             WHERE id = %s
        """, (mandate_id, self.id))
        self.set_attributes(mandate=mandate_id)

    def update_status(self, new_status):
        id = self.id
        if new_status == self.status:
            return
        self.db.run("""
            UPDATE exchange_routes
               SET status = %(new_status)s
             WHERE id = %(id)s
        """, locals())
        self.set_attributes(status=new_status)
