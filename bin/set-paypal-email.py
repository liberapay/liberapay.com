#!/usr/bin/env python
"""Set the PayPal email address for a user.

Usage:

    [gittip] $ heroku config -s -a gittip | foreman run -e /dev/stdin ./env/bin/python ./bin/set-paypal-email.py username user@example.com [first-eight-of-api-key] [overwrite]

"""
from __future__ import print_function

import sys

from gittip import wireup

if len(sys.argv) < 3:
    print("Usage: " + sys.argv[0] + " username user@example.com [first-eight-of-api-key] [overwrite]")
    sys.exit(1)

username = sys.argv[1] # will fail with KeyError if missing
email = sys.argv[2]

if len(sys.argv) < 4:
    first_eight = "unknown!"
else:
    first_eight = sys.argv[3]

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
    if len(sys.argv) < 5 or sys.argv[4] != "overwrite":
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
