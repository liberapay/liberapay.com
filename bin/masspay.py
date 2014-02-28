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
from decimal import Decimal as D

import requests
from httplib import IncompleteRead


os.chdir('../masspay')
ts = datetime.datetime.now().strftime('%Y-%m-%d')
INPUT_CSV = '{}.input.csv'.format(ts)
PAYPAL_CSV = '{}.output.paypal.csv'.format(ts)
GITTIP_CSV = '{}.output.gittip.csv'.format(ts)


def round_(d):
    return d.quantize(D('0.01'))

def print_rule(w=80):
    print("-" * w)


class Payee(object):
    username = None
    email = None
    gross = None
    gross_perc = None
    fee = None
    net = None
    additional_note = ""

    def __init__(self, rec):
        self.username, self.email, fee_cap, amount = rec
        self.gross = D(amount)
        self.fee = D(0)
        self.fee_cap = D(fee_cap)
        self.net = self.gross

    def assess_fee(self):
        fee = self.gross - round_(self.gross / D('1.02'))   # 2% fee
        fee = min(fee, self.fee_cap)                        # capped at $20, or $1 for U.S.
        self.fee += fee
        self.net -= fee
        if self.net % 1 == D('0.25'):

            # Prevent an escrow leak. It's complicated, but it goes something
            # like this:
            #
            #   1. We want to pass PayPal's fees through to each payee.
            #
            #   2. There is no option to have the receiver pay the fee, as
            #       there is with Instant Transfer.
            #
            #   3. We have to subtract the fee before uploading the spreadsheet
            #       to PayPal.
            #
            #   4. If we upload 15.24, PayPal upcharges to 15.54.
            #
            #   6. If we upload 15.25, PayPal upcharges to 15.56.
            #
            #   7. They only accept whole cents. We can't upload 15.245.
            #
            #   8. What if we want to hit 15.55?
            #
            #   9. We can't.
            #
            #  10. Our solution is to leave a penny behind in Gittip for
            #       affected payees.
            #
            # See also: https://github.com/gittip/www.gittip.com/issues/1673
            #           https://github.com/gittip/www.gittip.com/issues/2029

            self.gross -= D('0.01')
            self.net -= D('0.01')
            self.additional_note = "Penny remaining due to PayPal rounding limitation."
        return fee


def compute_input_csv():
    from gittip import wireup
    db = wireup.db(wireup.env())
    participants = db.all("""

        SELECT participants.*::participants
          FROM participants
         WHERE paypal_email IS NOT null
           AND balance > 0
      ORDER BY balance DESC

    """)
    writer = csv.writer(open(INPUT_CSV, 'w+'))
    print_rule(88)
    headers = "username", "email", "fee cap", "balance", "tips", "amount"
    print("{:<24}{:<32} {:^7} {:^7} {:^7} {:^7}".format(*headers))
    print_rule(88)
    total_gross = 0
    for participant in participants:
        tips, total = participant.get_tips_and_total(for_payday=False)
        amount = participant.balance - total
        if amount < 0.50:
            # Minimum payout of 50 cents. I think that otherwise PayPal upcharges to a penny.
            # See https://github.com/gittip/www.gittip.com/issues/1958.
            continue
        total_gross += amount
        print("{:<24}{:<32} {:>7} {:>7} {:>7} {:>7}".format( participant.username
                                                           , participant.paypal_email
                                                           , participant.paypal_fee_cap
                                                           , participant.balance
                                                           , total
                                                           , amount
                                                            ))
        row = (participant.username, participant.paypal_email, participant.paypal_fee_cap, amount)
        writer.writerow(row)
    print(" "*80, "-"*7)
    print("{:>88}".format(total_gross))


def compute_output_csvs():
    payees = [Payee(rec) for rec in csv.reader(open(INPUT_CSV))]
    payees.sort(key=lambda o: o.gross, reverse=True)

    total_fees = sum([payee.assess_fee() for payee in payees])  # side-effective!
    total_net = sum([p.net for p in payees])
    total_gross = sum([p.gross for p in payees])
    assert total_fees + total_net == total_gross

    paypal_csv = csv.writer(open(PAYPAL_CSV, 'w+'))
    gittip_csv = csv.writer(open(GITTIP_CSV, 'w+'))
    print_rule()
    print("{:<24}{:<32} {:^7} {:^7} {:^7}".format("username", "email", "gross", "fee", "net"))
    print_rule()
    for payee in payees:
        paypal_csv.writerow((payee.email, payee.net, "usd"))
        gittip_csv.writerow(( payee.username
                            , payee.email
                            , payee.gross
                            , payee.fee
                            , payee.net
                            , payee.additional_note
                             ))
        print("{username:<24}{email:<32} {gross:>7} {fee:>7} {net:>7}".format(**payee.__dict__))

    print(" "*56, "-"*23)
    print("{:>64} {:>7} {:>7}".format(total_gross, total_fees, total_net))


def post_back_to_gittip():

    try:
        gittip_api_key = os.environ['GITTIP_API_KEY']
    except KeyError:
        gittip_api_key = getpass.getpass("Gittip API key: ")

    try:
        gittip_base_url = os.environ['GITTIP_BASE_URL']
    except KeyError:
        gittip_base_url = 'https://www.gittip.com'

    for username, email, gross, fee, net, additional_note in csv.reader(open(GITTIP_CSV)):
        url = '{}/{}/history/record-an-exchange'.format(gittip_base_url, username)
        note = 'PayPal MassPay to {}.'.format(email)
        if additional_note:
            note += " " + additional_note
        print(note)

        data = {'amount': '-' + net, 'fee': fee, 'note': note}
        try:
            response = requests.post(url, auth=(gittip_api_key, ''), data=data)
        except IncompleteRead:
            print('IncompleteRead, proceeding (but double-check!)')
        else:
            if response.status_code != 200:
                if response.status_code == 404:
                    print('Got 404, is your API key good? {}'.format(gittip_api_key))
                else:
                    print('... resulted in a {} response:'.format(response.status_code))
                    print(response.text)
                raise SystemExit


def main():
    print("Looking for files for {} ...".format(ts))
    for filename in (INPUT_CSV, PAYPAL_CSV, GITTIP_CSV):
        print("  [{}] {}".format('x' if os.path.exists(filename) else ' ', filename))

    if not sys.argv[1:]:
        if raw_input("\nCompute input CSV? [y/N] ") == 'y':
            compute_input_csv()
        if raw_input("\nCompute output CSVs? [y/N] ") == 'y':
            compute_output_csvs()
        if raw_input("\nPost back to Gittip? [y/N] ") == 'y':
            post_back_to_gittip()

    else:
        if '-i' in sys.argv:
            compute_input_csv()
        if '-o' in sys.argv:
            compute_output_csvs()
        if '-p' in sys.argv:
            post_back_to_gittip()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
