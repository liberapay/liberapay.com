from __future__ import absolute_import, division, print_function, unicode_literals

import balanced
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
    def associate_balanced(cls, participant, balanced_account, network, address):
        if network == 'balanced-cc':
            obj = balanced.Card.fetch(address)
        else:
            assert network == 'balanced-ba', network # sanity check
            obj = balanced.BankAccount.fetch(address)
        obj.associate_to_customer(balanced_account)

        return cls.insert(participant, network, address)

    @classmethod
    def insert(cls, participant, network, address, error='', fee_cap=None):
        participant_id = participant.id
        r = cls.db.one("""
            INSERT INTO exchange_routes
                        (participant, network, address, error, fee_cap)
                 VALUES (%(participant_id)s, %(network)s, %(address)s, %(error)s, %(fee_cap)s)
              RETURNING exchange_routes.*::exchange_routes
        """, locals())
        if network == 'balanced-cc':
            participant.update_giving_and_tippees()
        r.__dict__['participant'] = participant
        return r

    def invalidate(self):
        if self.network.startswith('balanced-'):
            if self.network == 'balanced-cc':
                balanced.Card.fetch(self.address).unstore()
            else:
                assert self.network == 'balanced-ba'
                balanced.BankAccount.fetch(self.address).delete()
        self.update_error('invalidated')

    def update_error(self, new_error, propagate=True):
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

        # Update the receiving amounts of tippees if requested and necessary
        if not propagate or self.network != 'balanced-cc':
            return
        if self.participant.is_suspicious or bool(new_error) == bool(old_error):
            return
        self.participant.update_giving_and_tippees()
