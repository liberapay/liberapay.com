#!/usr/bin/env python
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import csv
from decimal import Decimal as D, ROUND_UP

import requests


gittip_api_key = os.environ['GITTIP_API_KEY']


def round_(d):
    return d.quantize(D('0.01'))

def round_up(d):
    return d.quantize(D('0.01'), ROUND_UP)


gittip = requests.session()
total_gross = total_fees = total_net = D('0.00')

class Payee(object):
    username = None
    email = None
    gross = None
    gross_perc = None
    fee = None
    net = None

    def __init__(self, rec):
        self.username, self.email, amount = rec
        self.gross = D(amount)
        self.fee = D(0)
        self.net = self.gross

    def assess_fee(self, fee):
        payee.fee += fee
        payee.net -= fee

infile = open('owed.csv')
outfile = open('masspay.csv', 'w+')

payees = [Payee(rec) for rec in csv.reader(infile)]
payees.sort(key=lambda o: o.gross)

total_gross = sum([p.gross for p in payees])
total_fees = total_gross - round_(total_gross / D('1.02'))  # 2% fee
total_net = 0

for payee in payees:
    payee.gross_perc = payee.gross / total_gross
    payee.assess_fee(round_(total_fees * payee.gross_perc))

fee_check = sum([p.fee for p in payees])
if fee_check != total_fees:

    # Up to one penny per payee is okay.
    fee_difference = total_fees - fee_check
    fee_tolerance = D('0.0{}'.format(len((payees)))) # one penny per payee
    print("-"*78)
    print()
    print("Fee rounding error tolerance:   {}".format(fee_tolerance))
    print("Accumulated fee rounding error: {}".format(fee_difference))
    print()
    assert fee_difference < fee_tolerance

    # Distribute rounding errors.
    for payee in reversed(payees):
        allotment = round_up(fee_difference * payee.gross_perc)
        payee.assess_fee(allotment)
        print("  {} => {}".format(allotment, payee.email))

        fee_difference -= allotment
        if fee_difference == 0:
            break
    print()

total_net = sum([p.net for p in payees])
fee_check = sum([p.fee for p in payees])
assert fee_check == total_fees
assert total_net + total_fees == total_gross

out = csv.writer(outfile)
print("-"*78)
print("{:<32} {:^6} {:^6} {:^6}".format("email", "gross", "fee", "net"))
print("-" * 78)
for payee in payees:
    out.writerow((payee.email, payee.net, "usd"))
    requests.post( 'https://www.gittip.com/{}/history/record-an-exchange'.format(payee.username)
                 , auth=(gittip_api_key, '')
                 , data={ 'amount': str(payee.net)
                        , 'fee': str(payee.fee)
                        , 'note': 'PayPal MassPay of ${} to {}'.format(payee.gross, payee.email)
                         }
                  )
    print("{email:<32} {gross:>6} {fee:>6} {net:>6}".format(**payee.__dict__))

print(" "*32, "-"*20)
print("{:>39} {:>6} {:>6}".format(total_gross, total_fees, total_net))
