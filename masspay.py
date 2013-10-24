#!/usr/bin/env python
"""This is a script for managing MassPay each week.

Most of our payouts are handled by Balanced, but they're limited to people in
the U.S. We need to payout to people outside the U.S. (#126), and while we work
on a long-term solution, we are using PayPal. However, we've grown past the
point that PayPal's Instant Transfer feature is workable. This script is for
interfacing with PayPal's MassPay feature.

This script provides for:

  1. Computing an input CSV by hitting the Gittip database directly.
  2. Computing two output CSVs (one to upload to PayPal, the second to use for POSTing
      the exchanges back to Gittip)
  3. POSTing the exchanges back to Gittip via the HTTP API.

The idea is that you run steps 1 and 2, then run through the MassPay UI on the
PayPal website using the appropriate CSV from step 2, then run step 3.

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import csv
import datetime
import getpass
import os
import sys
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


def compute_input_csv():
    from gittip import wireup
    db = wireup.db()
    participants = db.all("""

        SELECT participants.*::participants
          FROM participants
         WHERE paypal_email IS NOT null
           AND balance > 0
      ORDER BY balance DESC

    """)
    writer = csv.writer(open(INPUT_CSV, 'w+'))
    print_rule()
    print("{:<32} {} {:^5} {:^6}".format("email", "balance", "tips", "amount"))
    print_rule()
    total_gross = 0
    for participant in participants:
        tips, total = participant.get_tips_and_total(datetime.datetime.now())
        amount = participant.balance - total
        total_gross += amount
        print("{:<32} {:>6} {:>6} {:>6}"
              .format(participant.paypal_email, participant.balance, total, amount))
        row = (participant.username, participant.paypal_email, amount)
        writer.writerow(row)
    print(" "*46, "-"*6)
    print("{:>53}".format(total_gross))


def compute_output_csvs():
    payees = [Payee(rec) for rec in csv.reader(open(INPUT_CSV))]
    payees.sort(key=lambda o: o.gross, reverse=True)

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

    try:
        gittip_base_url = os.environ['GITTIP_BASE_URL']
    except KeyError:
        gittip_base_url = 'https://www.gittip.com'

    for username, email, gross, fee, net in csv.reader(open(GITTIP_CSV)):
        url = '{}/{}/history/record-an-exchange'.format(gittip_base_url, username)
        note = 'PayPal MassPay to {}.'.format(gross, email)
        data = {'amount': '-' + net, 'fee': fee, 'note': note}
        requests.post(url, auth=(gittip_api_key, ''), data=data)
        print(note)


def main():
    print("Looking for files for {} ...".format(ts))
    for filename in (INPUT_CSV, PAYPAL_CSV, GITTIP_CSV):
        print("  [{}] {}".format('x' if os.path.exists(filename) else ' ', filename))

    if not sys.argv[1:]:
        if raw_input("\nCompute input CSV? [y/N] ") == 'y':
            compute_input_csv()
        if raw_input("\nCompute output CSVs? [y/N] ") == 'y':
            compute_output_csvs()
        if raw_input("\nRecord exchanges in Gittip? [y/N] ") == 'y':
            record_exchanges_in_gittip()

    else:
        if '-i' in sys.argv:
            compute_input_csv()
        if '-o' in sys.argv:
            compute_output_csvs()
        if '-r' in sys.argv:
            record_exchanges_in_gittip()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
