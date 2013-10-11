#!/usr/bin/env python
from __future__ import absolute_import, division, print_function, unicode_literals

import csv
import datetime
import getpass
import os
from decimal import Decimal as D, ROUND_UP

import requests


os.chdir('../masspay')
ts = datetime.datetime.now().strftime('%Y-%m-%d')
INPUT_CSV = '{}.input.csv'.format(ts)
PAYPAL_CSV = '{}.output.paypal.csv'.format(ts)
GITTIP_CSV = '{}.output.gittip.csv'.format(ts)


def round_(d):
    return d.quantize(D('0.01'))

def round_up(d):
    return d.quantize(D('0.01'), ROUND_UP)

def print_rule():
    print("-" * 53)


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
        self.fee += fee
        self.net -= fee


def compute_output_csvs():
    payees = [Payee(rec) for rec in csv.reader(open(INPUT_CSV))]
    payees.sort(key=lambda o: o.gross)

    total_gross = sum([p.gross for p in payees])
    total_fees = total_gross - round_(total_gross / D('1.02'))  # 2% fee
    total_net = D('0.00')

    for payee in payees:
        payee.gross_perc = payee.gross / total_gross
        payee.assess_fee(round_(total_fees * payee.gross_perc))

    fee_check = sum([p.fee for p in payees])
    if fee_check != total_fees:

        # Up to one penny per payee is okay.
        fee_difference = total_fees - fee_check
        fee_tolerance = D('0.0{}'.format(len((payees)))) # one penny per payee
        print_rule()
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

    paypal_csv = csv.writer(open(PAYPAL_CSV, 'w+'))
    gittip_csv = csv.writer(open(GITTIP_CSV, 'w+'))
    print_rule()
    print("{:<32} {:^6} {:^6} {:^6}".format("email", "gross", "fee", "net"))
    print_rule()
    for payee in payees:
        paypal_csv.writerow((payee.email, payee.net, "usd"))
        gittip_csv.writerow(( payee.username
                            , payee.email
                            , payee.gross
                            , payee.fee
                            , payee.net
                             ))
        print("{email:<32} {gross:>6} {fee:>6} {net:>6}".format(**payee.__dict__))

    print(" "*32, "-"*20)
    print("{:>39} {:>6} {:>6}".format(total_gross, total_fees, total_net))


def record_exchanges_in_gittip():

    try:
        gittip_api_key = os.environ['GITTIP_API_KEY']
    except KeyError:
        gittip_api_key = getpass.getpass("Gittip API key: ")

    for username, email, gross, fee, net in csv.reader(open(GITTIP_CSV)):
        url = 'https://www.gittip.com/{}/history/record-an-exchange'.format(username)
        note = 'PayPal MassPay to {}.'.format(gross, email)
        data = {'amount': '-' + net, 'fee': fee, 'note': note}
        requests.post(url, auth=(gittip_api_key, ''), data=data)
        print(note)


def main():
    print("Looking for files for {} ...".format(ts))
    for filename in (INPUT_CSV, PAYPAL_CSV, GITTIP_CSV):
        print("  [{}] {}".format('x' if os.path.exists(filename) else ' ', filename))

    if raw_input("\nCompute output CSVs? [y/N] ") == 'y':
        compute_output_csvs()
    if raw_input("\nRecord exchanges in Gittip? [y/N] ") == 'y':
        record_exchanges_in_gittip()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
