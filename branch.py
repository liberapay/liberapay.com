"""Populate a Balanced test marketplace per a db.
"""
import balanced
from gittip import wireup


print "Wiring up ..."

env = wireup.env()
wireup.billing(env)
db = wireup.db(env)


print "Populating Balanced ..."

no_card_no_bank     = balanced.Customer(email='TEST-no-card-no-bank@gittip.com').save()
no_card_good_bank   = balanced.Customer(email='TEST-no-card-good-bank@gittip.com').save()
no_card_bad_bank    = balanced.Customer(email='TEST-no-card-bad-bank@gittip.com').save()
good_card_no_bank   = balanced.Customer(email='TEST-good-card-no-bank@gittip.com').save()
good_card_good_bank = balanced.Customer(email='TEST-good-card-good-bank@gittip.com').save()
good_card_bad_bank  = balanced.Customer(email='TEST-good-card-bad-bank@gittip.com').save()
bad_card_no_bank    = balanced.Customer(email='TEST-bad-card-no-bank@gittip.com').save()
bad_card_good_bank  = balanced.Customer(email='TEST-bad-card-good-bank@gittip.com').save()
bad_card_bad_bank   = balanced.Customer(email='TEST-bad-card-bad-bank@gittip.com').save()

no_card_no_bank
no_card_good_bank
no_card_bad_bank
good_card_no_bank
good_card_good_bank
good_card_bad_bank
bad_card_no_bank
bad_card_good_bank
bad_card_bad_bank

# https://docs.balancedpayments.com/1.1/overview/resources/#test-credit-card-numbers
good_card = lambda: balanced.Card( number="4111111111111111"
                                 , expiration_month="12"
                                 , expiration_year="2015").save()
bad_card = lambda: balanced.Card( number="4444444444444448"
                                , expiration_month="12"
                                , expiration_year="2015").save()

# https://docs.balancedpayments.com/1.1/overview/resources/#test-bank-account-numbers
good_bank = lambda: balanced.BankAccount( account_number="9900000002"
                                        , routing_number="021000021"
                                        , name="Foo").save()
bad_bank = lambda: balanced.BankAccount( account_number="9900000004"
                                       , routing_number="021000021"
                                       , name="Foo").save()

good_card().associate_to_customer(good_card_no_bank)
good_card().associate_to_customer(good_card_good_bank)
good_card().associate_to_customer(good_card_bad_bank)

bad_card().associate_to_customer(bad_card_no_bank)
bad_card().associate_to_customer(bad_card_good_bank)
bad_card().associate_to_customer(bad_card_bad_bank)

good_bank().associate_to_customer(no_card_good_bank)
good_bank().associate_to_customer(good_card_good_bank)
good_bank().associate_to_customer(bad_card_good_bank)

bad_bank().associate_to_customer(no_card_bad_bank)
bad_bank().associate_to_customer(good_card_bad_bank)
bad_bank().associate_to_customer(bad_card_bad_bank)


print "Updating DB ..."

participants = db.all("SELECT p.*::participants from participants p "
                      "WHERE balanced_customer_href IS NOT NULL")

for participant in participants:

    customer = None
    card = participant.last_bill_result
    bank = participant.last_ach_result

    if card is None:
        if bank is None:
            customer = no_card_no_bank
        elif bank == '':
            customer = no_card_good_bank
        elif bank > '':
            customer = no_card_bad_bank
    elif card == '':
        if bank is None:
            customer = good_card_no_bank
        elif bank == '':
            customer = good_card_good_bank
        elif bank > '':
            customer = good_card_bad_bank
    elif card > '':
        if bank is None:
            customer = bad_card_no_bank
        elif bank == '':
            customer = bad_card_good_bank
        elif bank > '':
            customer = bad_card_bad_bank

    print customer.href

    db.run( "UPDATE participants SET balanced_customer_href=%s WHERE id=%s"
          , (customer.href, participant.id))

print len(participants)
