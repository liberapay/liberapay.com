"""
This is a one-off script to populate the new `emails` table using the addresses
we have in `participants`.
"""
from __future__ import division, print_function, unicode_literals

from urllib import quote
import uuid

import gratipay
from aspen.utils import utcnow
from postgres.orm import Model

import gratipay.wireup

env = gratipay.wireup.env()
tell_sentry = gratipay.wireup.make_sentry_teller(env)
db = gratipay.wireup.db(env)
gratipay.wireup.mail(env)
gratipay.wireup.load_i18n('.', tell_sentry)
gratipay.wireup.canonical(env)


class EmailAddressWithConfirmation(Model):
    typname = "email_address_with_confirmation"

db.register_model(EmailAddressWithConfirmation)


def add_email(self, email):
    nonce = str(uuid.uuid4())
    verification_start = utcnow()

    scheme = gratipay.canonical_scheme
    host = gratipay.canonical_host
    username = self.username_lower
    quoted_email = quote(email)
    link = "{scheme}://{host}/{username}/emails/verify.html?email={quoted_email}&nonce={nonce}"
    self.send_email('initial',
                    email=email,
                    link=link.format(**locals()),
                    username=self.username,
                    include_unsubscribe=False)

    db.run("""
        INSERT INTO emails
                    (address, nonce, verification_start, participant)
             VALUES (%s, %s, %s, %s)
    """, (email, nonce, verification_start, self.username))


participants = db.all("""
    SELECT p.*::participants
      FROM participants p
     WHERE email IS NOT NULL
       AND NOT is_closed
       AND is_suspicious IS NOT true
       AND claimed_time IS NOT NULL;
""")
total = len(participants)
for i, p in enumerate(participants, 1):
    print('sending email to %s (%i/%i)' % (p.username, i, total))
    add_email(p, p.email.address)
