#!/usr/bin/env python
"""Distribute a balance as a final gift. This addresses part of #54.

Usage:

    [gittip] $ heroku config -s -a gittip | foreman run -e /dev/stdin ./env/bin/python ./bin/final-gift.py "username" [first-eight-of-api-key]

"""
from __future__ import print_function

import sys
from decimal import ROUND_DOWN, Decimal as D

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
if tipper.balance == 0:
    raise SystemExit

claimed_tips, claimed_total, unclaimed_tips, unclaimed_total = tipper.get_giving_for_profile()
transfers = []
distributed = D('0.00')

for tip in claimed_tips:
    if tip.amount == 0:
        continue
    rate = tip.amount / claimed_total
    pro_rated = (tipper.balance * rate).quantize(D('0.01'), ROUND_DOWN)
    distributed += pro_rated
    print( tipper.username.ljust(12)
         , tip.tippee.ljust(18)
         , str(tip.amount).rjust(6)
         , str(rate).ljust(32)
         , pro_rated
          )
    transfers.append([tip.tippee, pro_rated])

diff = tipper.balance - distributed
if diff != 0:
    print("Adjusting for rounding error of {}. Giving it to {}.".format(diff, transfers[0][0]))
    transfers[0][1] += diff  # Give it to the highest receiver.

with db.get_cursor() as cursor:
    for tippee, amount in transfers:
        assert amount > 0
        cursor.run( "UPDATE participants SET balance=balance - %s WHERE username=%s"
                  , (amount, tipper.username)
                   )
        cursor.run( "UPDATE participants SET balance=balance + %s WHERE username=%s"
                  , (amount, tippee)
                   )
        cursor.run( "INSERT INTO transfers (tipper, tippee, amount) VALUES (%s, %s, %s)"
                  , (tipper.username, tippee, amount)
                   )
