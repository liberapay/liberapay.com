#!/usr/bin/env python
"""This is a one-off script to update user_info for #1936.

This could be generalized for #900.

"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import time
import sys

import requests
from gittip import wireup
from requests_oauthlib import OAuth1

db = wireup.db(wireup.env())

def update_twitter():
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
        print(nremaining, reset, time.time())


        if response.status_code != 200:

            # Who knows what happened?
            # ========================
            # Supposedly we shouldn't hit 429, at least.

            print(response.status_code, response.text)

        else:

            # Update!
            # =======

            users = response.json()

            with db.get_cursor() as c:

                for user_info in users:

                    # flatten per upsert method in gittip/elsewhere/__init__.py
                    for k, v in user_info.items():
                        user_info[k] = unicode(v)

                    user_id = user_info['id']

                    c.one("""
                        UPDATE elsewhere
                        SET user_info=%s
                        WHERE user_id=%s
                        AND platform='twitter'
                        RETURNING id
                    """, (user_info, user_id))

                    print("updated {} ({})".format(user_info['screen_name'], user_id))

                # find deleted users
                existing = set(u['id'] for u in users)
                deleted = existing - set(batch)

                for user_id in deleted:

                    c.one("""
                        UPDATE elsewhere
                        SET user_info=NULL
                        WHERE user_id=%s
                        AND platform='twitter'
                        RETURNING id
                    """, (user_id,))

                    print("orphan found: {}".format(user_id))


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

def update_github():
    elsewhere = db.all("SELECT user_id FROM ELSEWHERE WHERE platform='github' ORDER BY id;")
    url = "https://api.github.com/user/%s"
    client_id = os.environ.get('GITHUB_CLIENT_ID')
    client_secret = os.environ.get('GITHUB_CLIENT_SECRET')

    for user_id in elsewhere:
        response = requests.get(url % user_id, params={
            'client_id': client_id,
            'client_secret': client_secret
        })

        # Log the rate-limit.
        # ===================

        nremaining = int(response.headers['X-RATELIMIT-REMAINING'])
        reset = int(response.headers['X-RATELIMIT-RESET'])
        # https://developer.github.com/v3/#rate-limiting
        now = time.time()
        print(nremaining, reset, now, reset-now, end=' ')

        status = response.status_code

        if status == 200:

            user_info = response.json()

            # flatten per upsert method in gittip/elsewhere/__init__.py
            for k, v in user_info.items():
                user_info[k] = unicode(v)

            assert user_id == user_info['id']

            db.one("""
                UPDATE elsewhere
                SET user_info=%s
                WHERE user_id=%s
                AND platform='github'
                RETURNING id
            """, (user_info, user_id))

            print("updated {} ({})".format(user_info['login'], user_id))

        elif status == 404:

            db.one("""
                UPDATE elsewhere
                SET user_info=NULL
                WHERE user_id=%s
                AND platform='github'
                RETURNING id
            """, (user_id,))

            print("orphan found: {}".format(user_id))
        else:
            # some other problem
            print(response.status_code, response.text)

        sleep_for = 0.5
        if nremaining == 0:
            sleep_for = reset - time.time()
            sleep_for += 10  # Account for potential clock skew between us and them
        time.sleep(sleep_for)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        platform = raw_input("twitter or github?: ")
    else:
        platform = sys.argv[1]

    if platform == 'twitter':
        update_twitter()
    elif platform == 'github':
        update_github()
