#!/usr/bin/env python
"""This is a script for managing MassPay each week.

Most of our payouts are handled by Balanced, but they're limited to people in
the U.S. We need to payout to people outside the U.S. (#126), and while we work
on a long-term solution, we are using PayPal. However, we've grown past the
point that PayPal's Instant Transfer feature is workable. This script is for
interfacing with PayPal's MassPay feature.

This script provides for:

  1. Computing an input CSV by hitting the Gratipay database directly.
  2. Computing two output CSVs (one to upload to PayPal, the second to use for POSTing
      the exchanges back to Gratipay)
  3. POSTing the exchanges back to Gratipay via the HTTP API.

The idea is that you run steps 1 and 2, then run through the MassPay UI on the
PayPal website using the appropriate CSV from step 2, then run step 3.

"""
from __future__ import absolute_import, division, print_function, unicode_literals

import csv
import datetime
import getpass
import os
import sys
from decimal import Decimal as D, ROUND_HALF_UP

import requests
from httplib import IncompleteRead


os.chdir('../masspay')
ts = datetime.datetime.now().strftime('%Y-%m-%d')
INPUT_CSV = '{}.input.csv'.format(ts)
PAYPAL_CSV = '{}.output.paypal.csv'.format(ts)
GITTIP_CSV = '{}.output.gratipay.csv'.format(ts)


def round_(d):
    return d.quantize(D('0.01'), rounding=ROUND_HALF_UP)

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

        # In order to avoid slowly leaking escrow, we need to be careful about
        # how we compute the fee. It's complicated, but it goes something like
        # this:
        #
        #   1. We want to pass PayPal's fees through to each payee.
        #
        #   2. With MassPay there is no option to have the receiver pay the fee,
        #       as there is with Instant Transfer.
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
        #  10. Our solution is to leave a penny behind in Gratipay for
        #       affected payees.
        #
        #  11. BUT ... if we upload 1.25, PayPal upcharges to 1.28. Think about
        #       it.
        #
        # See also: https://github.com/gratipay/www.gratipay.com/issues/1673
        #           https://github.com/gratipay/www.gratipay.com/issues/2029
        #           https://github.com/gratipay/www.gratipay.com/issues/2198
        #           https://github.com/gratipay/www.gratipay.com/pull/2209
        #           https://github.com/gratipay/www.gratipay.com/issues/2296

        target = net = self.gross
        while 1:
            net -= D('0.01')
            fee = round_(net * D('0.02'))
            fee = min(fee, self.fee_cap)
            gross = net + fee
            if gross <= target:
                break
        self.gross = gross
        self.net = net
        self.fee = fee

        remainder = target - gross
        if remainder > 0:
            n = "{:.2} remaining due to PayPal rounding limitation.".format(remainder)
            self.additional_note = n

        return fee


def compute_input_csv():
    from gratipay import wireup
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
        total = participant.giving + participant.pledging
        amount = participant.balance - total
        if amount < 0.50:
            # Minimum payout of 50 cents. I think that otherwise PayPal upcharges to a penny.
            # See https://github.com/gratipay/www.gratipay.com/issues/1958.
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
    gratipay_csv = csv.writer(open(GITTIP_CSV, 'w+'))
    print_rule()
    print("{:<24}{:<32} {:^7} {:^7} {:^7}".format("username", "email", "gross", "fee", "net"))
    print_rule()
    for payee in payees:
        paypal_csv.writerow((payee.email, payee.net, "usd"))
        gratipay_csv.writerow(( payee.username
                            , payee.email
                            , payee.gross
                            , payee.fee
                            , payee.net
                            , payee.additional_note
                             ))
        print("{username:<24}{email:<32} {gross:>7} {fee:>7} {net:>7}".format(**payee.__dict__))

    print(" "*56, "-"*23)
    print("{:>64} {:>7} {:>7}".format(total_gross, total_fees, total_net))


def post_back_to_gratipay():

    try:
        gratipay_api_key = os.environ['GITTIP_API_KEY']
    except KeyError:
        gratipay_api_key = getpass.getpass("Gratipay API key: ")

    try:
        gratipay_base_url = os.environ['GITTIP_BASE_URL']
    except KeyError:
        gratipay_base_url = 'https://www.gratipay.com'

    nposts = 0
    for username, email, gross, fee, net, additional_note in csv.reader(open(GITTIP_CSV)):
        url = '{}/{}/history/record-an-exchange'.format(gratipay_base_url, username)
        note = 'PayPal MassPay to {}.'.format(email)
        if additional_note:
            note += " " + additional_note
        print(note)

        data = {'amount': '-' + net, 'fee': fee, 'note': note}
        try:
            response = requests.post(url, auth=(gratipay_api_key, ''), data=data)
        except IncompleteRead:
            print('IncompleteRead, proceeding (but double-check!)')
        else:
            if response.status_code == 200:
                nposts += 1
            else:
                if response.status_code == 404:
                    print('Got 404, is your API key good? {}'.format(gratipay_api_key))
                else:
                    print('... resulted in a {} response:'.format(response.status_code))
                    print(response.text)
                raise SystemExit
        print("POSTed MassPay back to Gratipay for {} users.".format(nposts))


def run_report():
    """Print a report to help Determine how much escrow we should store in PayPal.
    """
    totals = []
    max_masspay = max_weekly_growth = D(0)
    for filename in os.listdir('.'):
        if not filename.endswith('.input.csv'):
            continue

        datestamp = filename.split('.')[0]

        totals.append(D(0))
        for rec in csv.reader(open(filename)):
            amount = rec[-1]
            totals[-1] += D(amount)

        max_masspay = max(max_masspay, totals[-1])
        if len(totals) == 1:
            print("{} {:8}".format(datestamp, totals[-1]))
        else:
            weekly_growth = totals[-1] / totals[-2]
            max_weekly_growth = max(max_weekly_growth, weekly_growth)
            print("{} {:8} {:4.1f}".format(datestamp, totals[-1], weekly_growth))

    print()
    print("Max Withdrawal:    ${:9,.2f}".format(max_masspay))
    print("Max Weekly Growth:  {:8.1f}".format(max_weekly_growth))
    print("5x Current:        ${:9,.2f}".format(5 * totals[-1]))


def main():
    if not sys.argv[1:]:
        print("Looking for files for {} ...".format(ts))
        for filename in (INPUT_CSV, PAYPAL_CSV, GITTIP_CSV):
            print("  [{}] {}".format('x' if os.path.exists(filename) else ' ', filename))
        print("Rerun with one of these options:")
        print("  -i - hits db to generate input CSV (needs envvars via heroku + honcho)")
        print("  -o - computes output CSVs (doesn't need anything but input CSV)")
        print("  -p - posts back to Gratipay (prompts for API key)")
    elif '-i' in sys.argv:
        compute_input_csv()
    elif '-o' in sys.argv:
        compute_output_csvs()
    elif '-p' in sys.argv:
        post_back_to_gratipay()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
