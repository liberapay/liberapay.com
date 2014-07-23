from __future__ import print_function

from invoke import run, task

import sys
import os

from gittip import wireup

@task(
    help={
        'username': "Gittip username. (required)",
        'email':    "PayPal email address. (required)",
        'api-key-fragment': "First 8 characters of user's API key.",
        'overwrite': "Override existing PayPal email?",
        'heroku': "Configure task for running directly via `heroku run`.",
    }
)
def set_paypal_email(username='', email='', api_key_fragment='', overwrite=False):
    """
    Usage:

    [gittip] $ env/bin/invoke set_paypal_email --username=username --email=user@example.com [--api-key-fragment=12e4s678] [--overwrite]
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
        print("No Gittip participant found with username '" + username + "'")
        sys.exit(2)

    # PayPal caps the MassPay fee at $20 for users outside the U.S., and $1 for
    # users inside the U.S. Most Gittip users using PayPal are outside the U.S.
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

def load_prod_envvars():
    print("Loading production environment variables...")

    output = run("heroku config --shell --app=gittip", warn=False, hide=True)
    envvars = output.stdout.split("\n")

    for envvar in envvars:
        if envvar:
            key, val = envvar.split("=")
            os.environ[key] = val
            print("Loaded " + key + ".")
