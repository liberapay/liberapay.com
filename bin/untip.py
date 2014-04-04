#!/usr/bin/env python
"""Zero out tips to a given user. This is a workaround for #1469.

Usage:

    [gittip] $ heroku config -s -a gittip | foreman run -e /dev/stdin ./env/bin/python ./scripts/untip.py "username"

"""
from __future__ import print_function

import sys

from gittip import wireup


tippee = sys.argv[1] # will fail with KeyError if missing

db = wireup.db(wireup.env())

tips = db.all("""

    SELECT amount
         , ( SELECT participants.*::participants
               FROM participants
              WHERE username=tipper
            ) AS tipper
         , ( SELECT participants.*::participants
               FROM participants
              WHERE username=tippee
            ) AS tippee
      FROM current_tips
     WHERE tippee = %s
       AND amount > 0
  ORDER BY amount DESC

""", (tippee,))


for tip in tips:
    print( tip.tipper.username.ljust(12)
         , tip.tippee.username.ljust(12)
         , str(tip.amount).rjust(6)
          )
    tip.tipper.set_tip_to(tip.tippee.username, '0.00')
