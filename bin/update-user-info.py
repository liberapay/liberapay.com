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
elsewhere = db.all("SELECT user_id FROM ELSEWHERE WHERE platform='twitter' ORDER BY id;")
url = "https://api.twitter.com/1.1/users/lookup.json"

while elsewhere:
    batch = elsewhere[:100]
    elsewhere = elsewhere[100:]
    user_ids = ','.join([str(user_id) for user_id in batch])

    response = requests.post(url, data={'user_id': user_ids}, auth=oauth)


    # Log the rate-limit.
    # ===================

    nremaining = int(response.headers['X-RATE-LIMIT-REMAINING'])
    reset = int(response.headers['X-RATE-LIMIT-RESET'])
    print nremaining, reset, time.time()


    if response.status_code != 200:

        # Who knows what happened?
        # ========================
        # Supposedly we shouldn't hit 429, at least.

        print response.status_code, response.text

    else:

        # Update!
        # =======

        users = response.json()

        for user_info in users:

            with db.get_cursor() as c:
                # flatten per upsert method in gittip/elsewhere/__init__.py
                for k, v in user_info.items():
                    user_info[k] = unicode(v)

                user_id = user_info['id']

                c.one("UPDATE elsewhere SET user_info=%s WHERE user_id=%s AND platform='twitter' RETURNING id", (user_info, user_id))

                print "updated {} ({})".format(user_info['screen_name'], user_id)


    # Stay under our rate limit.
    # =========================
    # We get 180 per 15 minutes for the users/lookup endpoint, per:
    #
    #   https://dev.twitter.com/docs/rate-limiting/1.1/limits

    sleep_for = 5
    if nremaining == 0:
        sleep_for = reset - time.time()
        sleep_for += 10  # Account for potential clock skew between us and Twitter.
    time.sleep(sleep_for)
