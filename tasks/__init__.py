from __future__ import print_function

from invoke import run, task

import sys
import os

from decimal import Decimal as D, ROUND_HALF_UP
import hashlib
import hmac
import requests
import time
import json

from gratipay import wireup
from gratipay.exceptions import NegativeBalance

MINIMUM_COINBASE_PAYOUT = 1 # in USD

@task(
    help={
        'username': "Gratipay username. (required)",
        'email':    "PayPal email address. (required)",
        'api-key-fragment': "First 8 characters of user's API key.",
        'overwrite': "Override existing PayPal email?",
        'heroku': "Configure task for running directly via `heroku run`.",
    }
)
def set_paypal_email(username='', email='', api_key_fragment='', overwrite=False):
    """
    Usage:

    [gratipay] $ env/bin/invoke set_paypal_email --username=username --email=user@example.com [--api-key-fragment=12e4s678] [--overwrite]
    """

    if not os.environ.get('DATABASE_URL'):
        load_prod_envvars()

    if not username or not email:
        print(set_paypal_email.__doc__)
        sys.exit(1)

    if not api_key_fragment:
        first_eight = "unknown!"
    else:
        first_eight = api_key_fragment

    db = wireup.db(wireup.env())

    FIELDS = """
            SELECT username, api_key, paypal_email
              FROM participants
             WHERE username = %s
    """

    fields = db.one(FIELDS, (username,))

    print(fields)

    if fields == None:
        print("No Gratipay participant found with username '" + username + "'")
        sys.exit(2)

    # PayPal caps the MassPay fee at $20 for users outside the U.S., and $1 for
    # users inside the U.S. Most Gratipay users using PayPal are outside the U.S.
    # so we set to $20 and I'll manually adjust to $1 when running MassPay and
    # noticing that something is off.
    FEE_CAP = ', paypal_fee_cap=20'

    if fields.paypal_email != None:
        print("PayPal email is already set to: " + fields.paypal_email)
        if not overwrite:
            print("Not overwriting existing PayPal email.")
            sys.exit(3)
        else:
            FEE_CAP = ''  # Don't overwrite fee_cap when overwriting email address.

    if fields.api_key == None:
        assert first_eight == "None"
    else:
        assert fields.api_key[0:8] == first_eight

    print("Setting PayPal email for " + username + " to " + email)

    SET_EMAIL = """
            UPDATE participants
               SET paypal_email=%s{}
             WHERE username=%s;
    """.format(FEE_CAP)
    print(SET_EMAIL % (email, username))

    db.run(SET_EMAIL, (email, username))

    print("All done.")

@task(
    help={
        'username': "Gratipay username. (required)",
        'amount': "Amount to send in USD. (required)",
        'api-key-fragment': "First 8 characters of user's API key.",
    }
)
def bitcoin_payout(username='', amount='', api_key_fragment=''):
    """
    Usage:

    [gratipay] $ env/bin/invoke bitcoin_payout --username=username --amount=amount [--api-key-fragment=12e4s678]
    """

    if not os.environ.get('DATABASE_URL'):
        load_prod_envvars()

    if not username or not amount:
        print(bitcoin_payout.__doc__)
        sys.exit(1)

    amount = D(amount)
    assert amount >= MINIMUM_COINBASE_PAYOUT
    amount = subtract_fee(amount)

    if not api_key_fragment:
        first_eight = "unknown!"
    else:
        first_eight = api_key_fragment

    db = wireup.db(wireup.env())

    FIELDS = """
            SELECT username, api_key, bitcoin_address, balance
              FROM participants
             WHERE username = %s
    """

    fields = db.one(FIELDS, (username,))

    print(fields)

    if fields == None:
        print("No Gratipay participant found with username '" + username + "'")
        sys.exit(2)

    if not fields.bitcoin_address:
        print(username + " hasn't linked a bitcoin address to their profile!")
        sys.exit(3)
    print("Fetching bitcoin_address from database: " + fields.bitcoin_address)
    bitcoin_address = fields.bitcoin_address

    if D(fields.balance) < D(amount):
        print("Not enough balance. %s only has %f in their account!" % username, D(amount))
        sys.exit(4)

    if fields.api_key == None:
        assert first_eight == "None"
    else:
        assert fields.api_key[0:8] == first_eight

    print("Sending bitcoin payout for " + username + " to " + bitcoin_address)
    try:
        data = {
            "transaction":{
                "to": bitcoin_address,
                "amount_string": str(amount),
                "amount_currency_iso": "USD",
                "notes": "Gratipay Bitcoin Payout",
                "instant_buy": True
            }
        }
        result = coinbase_request('https://api.coinbase.com/v1/transactions/send_money', json.dumps(data))

    except requests.HTTPError as e:
        print(e)
        return e

    if result.status_code != 200:
        print("Oops! Coinbase returned a " + str(result.status_code))
        print(result.json())
        sys.exit(5)
    elif result.json()['success'] != True:
        print("Coinbase transaction didn't succeed!")
        print(result.json())
        sys.exit(6)
    else:
        print("Coinbase transaction succeeded!")
        print("Entering Exchange in database")

        # Get the fee from the response
        fee_dict = result.json()['transfer']['fees']
        assert fee_dict['coinbase']['currency_iso'] == fee_dict['bank']['currency_iso'] == "USD"
        coinbase_fee = int(fee_dict['coinbase']['cents'])
        bank_fee = int(fee_dict['bank']['cents'])
        fee = (coinbase_fee + bank_fee) * D('0.01')

        # Get the amount from the response
        assert result.json()['transfer']['subtotal']['currency'] == "USD"
        amount = -D(result.json()['transfer']['subtotal']['amount']) # Negative amount for payouts
        btcamount = result.json()['transfer']['btc']['amount']

        note = "Sent %s btc to %s" % (btcamount, bitcoin_address)

        with db.get_cursor() as cursor:
            exchange_id = cursor.one("""
                INSERT INTO exchanges
                       (amount, fee, participant, note, status)
                VALUES (%s, %s, %s, %s, %s)
             RETURNING id
            """, (amount, fee, username, note, 'succeeded'))
            new_balance = cursor.one("""
                UPDATE participants
                   SET balance=(balance + %s)
                 WHERE username=%s
             RETURNING balance
            """, (amount - fee, username))
            if new_balance < 0:
                raise NegativeBalance
            print("Exchange recorded: " + str(exchange_id))
            print("New Balance: " + str(new_balance))

    print("All done.")

def round_(d):
    return d.quantize(D('0.01'), rounding=ROUND_HALF_UP)

def subtract_fee(amount):
    bank_fee = D('0.15')    # bank fee is $0.15
    net = target = amount - bank_fee
    while 1:                # coinbase fee is 1%; strategy borrowed from bin/masspay.py
        net -= D('0.01')
        coinbase_fee = round_(net * D('0.01'))
        gross = net + coinbase_fee
        if gross <= target:
            break
    return net

def coinbase_request(url, body=None):
    if not os.environ.get('COINBASE_API_KEY'):
        load_prod_envvars()
    nonce = int(time.time() * 1e6)
    message = str(nonce) + url + ('' if body is None else body)
    signature = hmac.new(str(os.environ['COINBASE_API_SECRET']), message, hashlib.sha256).hexdigest()

    headers = {
        'ACCESS_KEY' : os.environ['COINBASE_API_KEY'],
        'ACCESS_SIGNATURE': signature,
        'ACCESS_NONCE': nonce,
        'Accept': 'application/json'
    }

    # If we are passing data, a POST request is made. Note that content_type is specified as json.
    # try:
    if body:
        headers.update({'Content-Type': 'application/json'})
        return requests.post(url, data=body, headers=headers)
    # If body is nil, a GET request is made.
    else:
        return requests.get(url, headers=headers)

def load_prod_envvars():
    print("Loading production environment variables...")

    output = run("heroku config --shell --app=gratipay", warn=False, hide=True)
    envvars = output.stdout.split("\n")

    for envvar in envvars:
        if envvar:
            key, val = envvar.split("=", 1)
            os.environ[key] = val
            print("Loaded " + key + ".")
