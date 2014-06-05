#!/usr/bin/env python
"""Distribute a balance as a final gift. This addresses part of #54.

Usage:

    [gittip] $ heroku config -s -a gittip | foreman run -e /dev/stdin ./env/bin/python ./bin/final-gift.py "username" [first-eight-of-api-key]

"""
from __future__ import print_function

import sys

from gittip import wireup
from gittip.models.participant import Participant

db = wireup.db(wireup.env())

username = sys.argv[1] # will fail with KeyError if missing
tipper = Participant.from_username(username)
if len(sys.argv) < 3:
    first_eight = "unknown!"
else:
    first_eight = sys.argv[2]

# Ensure user is legit
FIELDS = """
        SELECT username, username_lower, api_key, claimed_time
          FROM participants
         WHERE username = %s
"""

fields = db.one(FIELDS, (username,))
print(fields)

if fields.api_key == None:
    assert first_eight == "None"
else:
    assert fields.api_key[0:8] == first_eight

print("Distributing {} from {}.".format(tipper.balance, tipper.username))
tipper.distribute_balance_as_final_gift()
