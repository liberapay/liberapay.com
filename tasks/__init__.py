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
    }
)
def set_paypal_email(username='', email='', api_key_fragment='', overwrite=False):
    """
    Usage:

    [gittip] $ env/bin/invoke set_paypal_email -u username -p user@example.com [-a 12e4s678] [--overwrite]
    """

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

    if fields.paypal_email != None:
        print("PayPal email is already set to: " + fields.paypal_email)
        if not overwrite:
            print("Not overwriting existing PayPal email.")
            sys.exit(3)

    if fields.api_key == None:
        assert first_eight == "None"
    else:
        assert fields.api_key[0:8] == first_eight

    print("Setting PayPal email for " + username + " to " + email)

    SET_EMAIL = """
            UPDATE participants
               SET paypal_email=%s
             WHERE username=%s;
    """
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
