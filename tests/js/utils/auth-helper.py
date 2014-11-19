#!/usr/bin/env python

from __future__ import print_function, unicode_literals

import os
import sys
import uuid

from datetime import timedelta

from aspen.utils import utcnow

import gratipay

from gratipay import wireup
from gratipay.models.participant import Participant


if len(sys.argv) < 2:
    sys.exit('Usage: %s <user>' % sys.argv[0])


db = Participant.db = wireup.db(wireup.env())
gratipay.RESTRICTED_USERNAMES = os.listdir('./www/')

username = sys.argv[1]
session_token = uuid.uuid4().hex
session_expires = utcnow() + timedelta(hours=6)


try:
    participant = Participant.from_username(username)
    participant.db = db
except:
    participant = Participant.with_random_username()
    participant.db = db
    participant.change_username(username)
    participant.set_as_claimed()

participant.update_session(session_token, session_expires)
print(session_token)
