from __future__ import absolute_import, division, print_function, unicode_literals

from mangopay.resources import Card, Mandate
from postgres.orm import Model


class ExchangeRoute(Model):

    typname = "exchange_routes"

    def __bool__(self):
        return self.error != 'invalidated'

    __nonzero__ = __bool__

    @classmethod
    def from_id(cls, id):
        return cls.db.one("""
            SELECT r.*::exchange_routes
              FROM exchange_routes r
             WHERE id = %(id)s
        """, locals())

    @classmethod
    def from_network(cls, participant, network):
        participant_id = participant.id
        r = cls.db.all("""
            SELECT r.*::exchange_routes
              FROM exchange_routes r
             WHERE participant = %(participant_id)s
               AND network = %(network)s
               AND COALESCE(error, '') <> 'invalidated'
          ORDER BY r.id DESC
        """, locals())
        for route in r:
            route.__dict__['participant'] = participant
        return r

    @classmethod
    def from_address(cls, participant, network, address):
        participant_id = participant.id
        r = cls.db.one("""
            SELECT r.*::exchange_routes
              FROM exchange_routes r
             WHERE participant = %(participant_id)s
               AND network = %(network)s
               AND address = %(address)s
        """, locals())
        if r:
            r.__dict__['participant'] = participant
        return r

    @classmethod
    def insert(cls, participant, network, address, error='', one_off=False):
        p_id = participant.id
        remote_user_id = participant.mangopay_user_id
        r = cls.db.one("""
            INSERT INTO exchange_routes
                        (participant, network, address, error, one_off, remote_user_id)
                 VALUES (%(p_id)s, %(network)s, %(address)s, %(error)s, %(one_off)s, %(remote_user_id)s)
              RETURNING exchange_routes.*::exchange_routes
        """, locals())
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
