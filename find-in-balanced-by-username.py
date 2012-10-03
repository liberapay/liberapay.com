#!./env/bin/python
"""This is a workaround for https://github.com/balanced/balanced-api/issues/141

Usage (tested on Mac OS):

    [gittip] $ open `heroku config | swaddle - ./find-in-balanced-by-username.py foobar 2> /dev/null`

The script will search for the user and print out the URI of their page in the
Balanced dashboard, and open will open it in your default web browser.

"""
import sys

import balanced
from gittip import wireup


wireup.billing()


email_address = sys.argv[1] + "@gittip.com"  # hack into an email address
api_uri = balanced.Account.query.filter(email_address=email_address).one().uri
dashboard_uri = "https://www.balancedpayments.com/" + api_uri[4:]
print dashboard_uri
