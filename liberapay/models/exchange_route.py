from __future__ import absolute_import, division, print_function, unicode_literals

from mangopay.resources import Card, Mandate
from postgres.orm import Model


class ExchangeRoute(Model):

    typname = "exchange_routes"

    def __bool__(self):
        return self.error != 'invalidated'

    __nonzero__ = __bool__

    @classmethod
    def from_id(cls, participant, id):
        route = cls.db.one("""
            SELECT r
              FROM exchange_routes r
             WHERE r.id = %(r_id)s
               AND r.participant = %(p_id)s
        """, dict(r_id=id, p_id=participant.id))
        if route:
            route.__dict__['participant'] = participant
        return route

    @classmethod
    def from_network(cls, participant, network, currency=None):
        participant_id = participant.id
        mangopay_user_id = participant.mangopay_user_id
        r = cls.db.all("""
            SELECT r
              FROM exchange_routes r
             WHERE participant = %(participant_id)s
               AND remote_user_id = %(mangopay_user_id)s
               AND network = %(network)s
               AND COALESCE(error, '') <> 'invalidated'
               AND COALESCE(currency::text, '') = COALESCE(%(currency)s::text, '')
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
    def insert(cls, participant, network, address, error='', one_off=False, currency=None):
        p_id = participant.id
        remote_user_id = participant.mangopay_user_id
        r = cls.db.one("""
            INSERT INTO exchange_routes
                        (participant, network, address, error, one_off, remote_user_id, currency)
                 VALUES (%(p_id)s, %(network)s, %(address)s, %(error)s, %(one_off)s,
                         %(remote_user_id)s, %(currency)s)
              RETURNING exchange_routes.*::exchange_routes
        """, locals())
        r.__dict__['participant'] = participant
        return r

    @classmethod
    def upsert_bankwire_route(cls, participant):
        r = cls.db.one("""
            INSERT INTO exchange_routes AS r
                        (participant, network, address, one_off, error, remote_user_id)
                 VALUES (%s, 'mango-bw', 'x', false, '', %s)
            ON CONFLICT (participant, network, address) DO UPDATE
                    SET one_off = false  -- dummy update
              RETURNING r
        """, (participant.id, participant.mangopay_user_id))
        r.__dict__['participant'] = participant
        return r

    def invalidate(self, obj=None):
        if self.network == 'mango-cc':
            card = obj or Card.get(self.address)
            if card.Active:
                card.Active = False
                card.save()
                assert card.Active is False, card.Active
        if self.mandate:
            mandate = Mandate.get(self.mandate)
            if mandate.Status in ('SUBMITTED', 'ACTIVE'):
                mandate.cancel()
        self.update_error('invalidated')

    def set_mandate(self, mandate_id):
        self.db.run("""
            UPDATE exchange_routes
               SET mandate = %s
             WHERE id = %s
        """, (mandate_id, self.id))
        self.set_attributes(mandate=mandate_id)

    def update_error(self, new_error):
        id = self.id
        old_error = self.error
        if old_error == 'invalidated':
            return
        self.db.run("""
            UPDATE exchange_routes
               SET error = %(new_error)s
             WHERE id = %(id)s
        """, locals())
        self.set_attributes(error=new_error)
