from calendar import monthrange
from datetime import date

from cached_property import cached_property
from postgres.orm import Model
import stripe

from ..constants import CARD_BRANDS
from ..exceptions import InvalidId, TooManyAttempts


class ExchangeRoute(Model):

    typname = "exchange_routes"

    def __bool__(self):
        return self.status in ('pending', 'chargeable')

    def __repr__(self):
        return '<ExchangeRoute id=%r participant=%r network=%r status=%r>' % (
            self.id, self.participant, self.network, self.status
        )

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
        r = cls.db.all("""
            SELECT r
              FROM exchange_routes r
             WHERE participant = %(participant_id)s
               AND network::text = %(network)s
               AND status = 'chargeable'
               AND COALESCE(currency::text, '') = COALESCE(%(currency)s::text, '')
               AND (one_off IS FALSE OR ctime > (current_timestamp - interval '6 hours'))
          ORDER BY r.is_default NULLS LAST, r.id DESC
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
        cls.db.hit_rate_limit('add_payment_instrument', str(p_id), TooManyAttempts)
        r = cls.db.one("""
            INSERT INTO exchange_routes AS r
                        (participant, network, address, status,
                         one_off, remote_user_id, country, currency)
                 VALUES (%(p_id)s, %(network)s, %(address)s, %(status)s,
                         %(one_off)s, %(remote_user_id)s, %(country)s, %(currency)s)
            ON CONFLICT (participant, network, address) DO NOTHING
              RETURNING r
        """, locals()) or cls.db.one("""
            SELECT r
              FROM exchange_routes r
             WHERE participant = %s
               AND network = %s
               AND address = %s
        """, (p_id, network, address))
        r.__dict__['participant'] = participant
        return r

    @classmethod
    def upsert_generic_route(cls, participant, network):
        if network == 'paypal':
            remote_user_id = 'x'
        else:
            raise NotImplementedError(network)
        r = cls.db.one("""
            INSERT INTO exchange_routes AS r
                        (participant, network, address, one_off, status, remote_user_id)
                 VALUES (%s, %s, 'x', false, 'chargeable', %s)
            ON CONFLICT (participant, network, address) DO UPDATE
                    SET one_off = excluded.one_off
                      , status = excluded.status
                      , remote_user_id = excluded.remote_user_id
              RETURNING r
        """, (participant.id, network, remote_user_id))
        r.__dict__['participant'] = participant
        return r

    @classmethod
    def attach_stripe_payment_method(cls, participant, pm, one_off):
        if pm.type == 'card':
            network = 'stripe-card'
        elif pm.type == 'sepa_debit':
            network = 'stripe-sdd'
        else:
            raise NotImplementedError(pm.type)
        customer_id = cls.db.one("""
            SELECT remote_user_id
              FROM exchange_routes
             WHERE participant = %s
               AND network::text LIKE 'stripe-%%'
             LIMIT 1
        """, (participant.id,))
        if customer_id:
            pm = stripe.PaymentMethod.attach(
                pm.id, customer=customer_id,
                idempotency_key='attach_%s_to_%s' % (pm.id, customer_id),
            )
        else:
            customer_id = stripe.Customer.create(
                email=participant.get_email_address(),
                payment_method=pm.id,
                idempotency_key='create_customer_for_participant_%i_with_%s' % (
                    participant.id, pm.id
                ),
            ).id
        pm_country = getattr(getattr(pm, pm.type), 'country', None)
        pm_currency = getattr(getattr(pm, pm.type), 'currency', None)
        route = cls.insert(
            participant, network, pm.id, 'chargeable',
            one_off=one_off, remote_user_id=customer_id,
            country=pm_country, currency=pm_currency,
        )
        route.stripe_payment_method = pm
        return route

    @classmethod
    def attach_stripe_source(cls, participant, source, one_off):
        if source.type == 'sepa_debit':
            network = 'stripe-sdd'
        elif source.type == 'card':
            network = 'stripe-card'
        else:
            raise NotImplementedError(source.type)
        customer_id = cls.db.one("""
            SELECT remote_user_id
              FROM exchange_routes
             WHERE participant = %s
               AND network::text LIKE 'stripe-%%'
             LIMIT 1
        """, (participant.id,))
        if customer_id:
            customer = stripe.Customer.retrieve(customer_id)
            customer.sources.create(
                source=source.id,
                idempotency_key='attach_%s_to_%s' % (source.id, customer_id),
            )
            del customer
        else:
            customer_id = stripe.Customer.create(
                email=source.owner.email,
                source=source.id,
                idempotency_key='create_customer_for_participant_%i_with_%s' % (
                    participant.id, source.id
                ),
            ).id
        source_country = getattr(getattr(source, source.type), 'country', None)
        source_currency = getattr(getattr(source, source.type), 'currency', None)
        route = ExchangeRoute.insert(
            participant, network, source.id, source.status,
            one_off=one_off, remote_user_id=customer_id,
            country=source_country, currency=source_currency,
        )
        route.stripe_source = source
        return route

    def invalidate(self, obj=None):
        if self.network.startswith('stripe-'):
            if self.address.startswith('pm_'):
                stripe.PaymentMethod.detach(self.address)
            else:
                try:
                    source = stripe.Source.retrieve(self.address).detach()
                except stripe.error.InvalidRequestError as e:
                    ignore = (
                        "does not appear to be currently attached" in str(e) or
                        "No such source: " in str(e)
                    )
                    if ignore:
                        pass
                    else:
                        raise
                else:
                    assert source.status not in ('chargeable', 'pending')
                    self.update_status(source.status)
                    return
        self.update_status('canceled')

    def set_as_default(self):
        with self.db.get_cursor() as cursor:
            cursor.run("""
                UPDATE exchange_routes
                   SET is_default = NULL
                 WHERE participant = %(p_id)s
                   AND is_default IS NOT NULL;
                UPDATE exchange_routes
                   SET is_default = true
                 WHERE participant = %(p_id)s
                   AND id = %(route_id)s
            """, dict(p_id=self.participant.id, route_id=self.id))
            self.participant.add_event(cursor, 'set_default_route', dict(
                id=self.id, network=self.network
            ))

    def set_as_default_for(self, currency):
        with self.db.get_cursor() as cursor:
            cursor.run("""
                UPDATE exchange_routes
                   SET is_default_for = NULL
                 WHERE participant = %(p_id)s
                   AND is_default_for = %(currency)s;
                UPDATE exchange_routes
                   SET is_default_for = %(currency)s
                 WHERE participant = %(p_id)s
                   AND id = %(route_id)s
            """, dict(p_id=self.participant.id, route_id=self.id, currency=currency))
            self.participant.add_event(cursor, 'set_default_route_for', dict(
                id=self.id, network=self.network, currency=currency,
            ))

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

    def get_brand(self):
        if self.network == 'stripe-card':
            if self.address.startswith('pm_'):
                brand = self.stripe_payment_method.card.brand
                return CARD_BRANDS.get(brand, brand)
            else:
                return self.stripe_source.card.brand
        elif self.network == 'stripe-sdd':
            if self.address.startswith('pm_'):
                raise NotImplementedError()
            else:
                return getattr(self.stripe_source.sepa_debit, 'bank_name', '')
        else:
            raise NotImplementedError(self.network)

    def get_expiration_date(self):
        if self.network == 'stripe-card':
            if self.address.startswith('pm_'):
                card = self.stripe_payment_method.card
            else:
                card = self.stripe_source.card
            day = monthrange(card.exp_year, card.exp_month)[-1]
            return date(card.exp_year, card.exp_month, day)
        elif self.network == 'stripe-sdd':
            return None
        else:
            raise NotImplementedError(self.network)

    def get_mandate_url(self):
        if self.network == 'stripe-card':
            return
        elif self.network == 'stripe-sdd':
            if self.address.startswith('pm_'):
                raise NotImplementedError()
            else:
                return self.stripe_source.sepa_debit.mandate_url
        else:
            raise NotImplementedError(self.network)

    def get_partial_number(self):
        if self.network == 'stripe-card':
            if self.address.startswith('pm_'):
                return '⋯' + str(self.stripe_payment_method.card.last4)
            else:
                return '⋯' + str(self.stripe_source.card.last4)
        elif self.network == 'stripe-sdd':
            from ..payin.stripe import get_partial_iban
            if self.address.startswith('pm_'):
                raise NotImplementedError()
            else:
                return get_partial_iban(self.stripe_source.sepa_debit)
        else:
            raise NotImplementedError(self.network)

    def get_postal_address(self):
        if self.network.startswith('stripe-'):
            if self.address.startswith('pm_'):
                return self.stripe_payment_method.billing_details.address
            else:
                return self.stripe_source.owner.address
        else:
            raise NotImplementedError(self.network)

    def set_postal_address(self, addr):
        if self.network.startswith('stripe-'):
            addr = addr.copy()
            addr['state'] = addr.pop('region')
            lines = addr.pop('local_address', '').splitlines()
            addr['line1'] = lines[0] if lines else None
            addr['line2'] = lines[1] if len(lines) > 1 else None
            if self.address.startswith('pm_'):
                self.stripe_payment_method = stripe.PaymentMethod.modify(
                    self.address,
                    billing_details={'address': addr},
                )
            else:
                self.stripe_source = stripe.Source.modify(
                    self.address,
                    owner={'address': addr},
                )
        else:
            raise NotImplementedError(self.network)

    def has_been_charged_successfully(self):
        return bool(self.db.one("""
            SELECT 1
              FROM payins pi
             WHERE pi.payer = %s
               AND pi.route = %s
               AND pi.status = 'succeeded'
             LIMIT 1
        """, (self.participant.id, self.id)))

    @cached_property
    def stripe_payment_method(self):
        return stripe.PaymentMethod.retrieve(self.address)

    @cached_property
    def stripe_source(self):
        return stripe.Source.retrieve(self.address)

    def sync_status(self):
        if self.address.startswith('pm_'):
            # A PaymentMethod doesn't have a status.
            return
        else:
            source = stripe.Source.retrieve(self.address)
            self.update_status(source.status)
            self.stripe_source = source
