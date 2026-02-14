"""This script is a simple wrapper around the `stripe listen` command.
"""

import json
import os
import re
import subprocess

from liberapay.website import website


website.wireup()
api_key = website.app_conf.stripe_secret_key

# Get the Stripe webhook secret
webhook_secret = subprocess.run(
    ['stripe', 'listen', '--api-key', api_key, '--print-secret'],
    stdout=subprocess.PIPE, check=True, universal_newlines=True,
).stdout.strip()
assert re.fullmatch(r'whsec_\w{32,}', webhook_secret), repr(webhook_secret)

# Insert the secret into the database
website.db.run("""
    INSERT INTO app_conf
                (key, value)
         VALUES ('stripe_callback_secret', %s)
    ON CONFLICT (key) DO UPDATE
            SET value = excluded.value
""", (json.dumps(webhook_secret),))

# Execute `stripe listen`
callback_url = website.canonical_url + '/callbacks/stripe'
os.execvp(
    'stripe',
    ['stripe', 'listen', '--api-key', api_key, '--forward-to', callback_url]
)
