#!/usr/bin/env python
"""This is a one-off script to update user_info for #1936.

This could be generalized for #900.

"""
import os
import time

import requests
from gittip import wireup
from requests_oauthlib import OAuth1


db = wireup.db()
oauth = OAuth1( os.environ['TWITTER_CONSUMER_KEY']
              , os.environ['TWITTER_CONSUMER_SECRET']
              , os.environ['TWITTER_ACCESS_TOKEN']
              , os.environ['TWITTER_ACCESS_TOKEN_SECRET']
               )
elsewhere = db.all("SELECT user_id FROM ELSEWHERE WHERE platform='twitter';")
url = "https://api.twitter.com/1.1/users/show.json?user_id=%s"

for user_id in elsewhere:
    response = requests.get(url % user_id, auth=oauth)

    if response.status_code != 200:
        # Who knows what happened? Bail.
        # (Supposedly we shouldn't hit 429, at least).
        print response.status_code
        print response.text
        raise SystemExit


    # Update!
    # =======

    user_info = response.json()

    # flatten per upsert method in gittip/elsewhere/__init__.py
    for k, v in user_info.items():
        user_info[k] = unicode(v)

    db.run("UPDATE elsewhere SET user_info=%s WHERE user_id=%s", (user_info, user_id))


    # Stay under our rate limit.
    # =========================
    # We get 180 per 15 minutes for the users/show endpoint, per:
    #
    #   https://dev.twitter.com/docs/rate-limiting/1.1/limits

    print response.headers['X-RATE-LIMIT-REMAINING']
    nremaining = int(response.headers['X-RATE-LIMIT-REMAINING'])
    sleep_for = 5
    if nremaining < 180:
        reset = int(response.headers['X-RATE-LIMIT-RESET'])
        sleep_for = reset - time.time()
        sleep_for += 10  # Account for potential clock skew between us and Twitter.
    time.sleep(sleep_for)
