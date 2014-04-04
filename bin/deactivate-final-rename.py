#!/usr/bin/env python
"""The final rename and clear step for deactivating an account.

If the account has a balance or is involved in active tips,
this script will report the problem and abort without making any update.

If the first eight digits of the account's API key are not given or do not match,
this script will report the problem and abort without making any update.

Usage:

    [gittip] $ heroku config -s -a gittip | foreman run -e /dev/stdin ./env/bin/python ./bin/deactivate-final-rename.py "username" [first-eight-of-api-key]

"""
from __future__ import print_function

import sys

from gittip import wireup
from gittip.models.participant import Participant


username = sys.argv[1] # will fail with KeyError if missing
if len(sys.argv) < 3:
    first_eight = "unknown!"
else:
    first_eight = sys.argv[2]

db = wireup.db(wireup.env())

target = Participant.from_username(username)

INCOMING = """
        SELECT count(*)
          FROM current_tips
         WHERE tippee = %s
           AND amount > 0
"""

FIELDS = """
        SELECT username, username_lower, api_key, claimed_time
          FROM participants
         WHERE username = %s
"""


incoming = db.one(INCOMING, (username,))
fields = db.one(FIELDS, (username,))

print("Current balance ", target.balance)
print("Incoming tip count ", incoming)
print(fields)

assert target.balance == 0
assert incoming == 0
if fields.api_key == None:
    assert first_eight == "None"
else:
    assert fields.api_key[0:8] == first_eight

deactivated_name = "deactivated-" + username
print("Renaming " + username + " to " + deactivated_name)

RENAME = """
        UPDATE participants
           SET claimed_time = null
             , session_token = null
             , username = %s
             , username_lower = %s
         WHERE username = %s
"""

print(RENAME % (deactivated_name, deactivated_name.lower(), username))

db.run(RENAME, (deactivated_name, deactivated_name.lower(), username))

print("All done.")
