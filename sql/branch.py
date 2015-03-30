import balanced

from gratipay import wireup
from gratipay.models import check_db

env = wireup.env()
db = wireup.db(env)
wireup.billing(env)


# https://docs.balancedpayments.com/1.1/api/customers/
CUSTOMER_LINKS = {
    "customers.bank_accounts": "/customers/{customers.id}/bank_accounts",
    "customers.card_holds": "/customers/{customers.id}/card_holds",
    "customers.cards": "/customers/{customers.id}/cards",
    "customers.credits": "/customers/{customers.id}/credits",
    "customers.debits": "/customers/{customers.id}/debits",
    "customers.destination": "/resources/{customers.destination}",
    "customers.disputes": "/customers/{customers.id}/disputes",
    "customers.external_accounts": "/customers/{customers.id}/external_accounts",
    "customers.orders": "/customers/{customers.id}/orders",
    "customers.refunds": "/customers/{customers.id}/refunds",
    "customers.reversals": "/customers/{customers.id}/reversals",
    "customers.source": "/resources/{customers.source}",
    "customers.transactions": "/customers/{customers.id}/transactions"
}


def customer_from_href(href):
    """This functions "manually" builds a minimal Customer instance.
    """
    id = href.rsplit('/', 1)[1]
    d = {'href': href, 'id': id, 'links': {}, 'meta': {}}
    return balanced.Customer(customers=[d], links=CUSTOMER_LINKS)


with db.get_cursor() as cursor:

    def insert_exchange_route(participant, network, address, error):
        cursor.run("""
            INSERT INTO exchange_routes
                        (participant, network, address, error)
                 VALUES (%(participant)s, %(network)s, %(address)s, %(error)s)
        """, locals())

    participants = cursor.all("""
        SELECT p.*::participants
          FROM participants p
         WHERE balanced_customer_href IS NOT NULL
           AND (last_bill_result IS NOT NULL OR last_ach_result IS NOT NULL)
    """)
    total = len(participants)

    for i, p in enumerate(participants, 1):
        if i % 100 == 1:
            print("processing participant %i/%i" % (i, total))
        customer = customer_from_href(p.balanced_customer_href)
        if p.last_bill_result != None:
            card = customer.cards.one()
            insert_exchange_route(p.id, 'balanced-cc', card.href, p.last_bill_result)
        if p.last_ach_result != None:
            ba = customer.bank_accounts.one()
            insert_exchange_route(p.id, 'balanced-ba', ba.href, p.last_ach_result)
