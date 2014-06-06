#!/usr/bin/env python
"""Zero out tips to a given user. This is a workaround for #1469.

Usage:

    [gittip] $ heroku config -s -a gittip | foreman run -e /dev/stdin ./env/bin/python ./scripts/untip.py "username"

"""
from __future__ import print_function

import sys

from gittip import wireup
from gittip.models.participant import Participant


tippee = sys.argv[1] # will fail with KeyError if missing
db = wireup.db(wireup.env())
Participant.from_username(tippee).clear_tips_receiving()
