from __future__ import absolute_import, division, print_function, unicode_literals

from postgres.orm import Model

from liberapay.billing import mangoapi


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
        r = cls.db.one("""
            SELECT r.*::exchange_routes
              FROM current_exchange_routes r
             WHERE participant = %(participant_id)s
               AND network = %(network)s
        """, locals())
        if r:
            r.__dict__['participant'] = participant
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
        r = cls.db.one("""
            INSERT INTO exchange_routes
                        (participant, network, address, error, one_off)
                 VALUES (%(p_id)s, %(network)s, %(address)s, %(error)s, %(one_off)s)
              RETURNING exchange_routes.*::exchange_routes
        """, locals())
        r.__dict__['participant'] = participant
        return r

    def invalidate(self, obj=None):
        if self.network == 'mango-cc':
            card = obj or mangoapi.cards.Get(self.address)
            if card.Active:
                card.Active = 'false'
                card = mangoapi.cards.Update(card)
                assert card.Active is False, card.Active
        self.update_error('invalidated')

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
