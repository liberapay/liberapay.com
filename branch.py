"""
This is a one-off script to populate the new `emails` table using the addresses
we have in `participants` and `elsewhere`.
"""
from __future__ import division, print_function, unicode_literals

import uuid

from aspen.utils import utcnow
from postgres.orm import Model

import gratipay.wireup

env = gratipay.wireup.env()
tell_sentry = gratipay.wireup.make_sentry_teller(env)
db = gratipay.wireup.db(env)
gratipay.wireup.mail(env)
gratipay.wireup.load_i18n('.', tell_sentry)


class EmailAddressWithConfirmation(Model):
    typname = "email_address_with_confirmation"

db.register_model(EmailAddressWithConfirmation)


def add_email(self, email):
    nonce = str(uuid.uuid4())
    ctime = utcnow()
    db.run("""
        INSERT INTO emails
                    (address, nonce, ctime, participant)
             VALUES (%s, %s, %s, %s)
    """, (email, nonce, ctime, self.username))

    username = self.username_lower
    link = "https://gratipay.com/{username}/verify-email.html?email={email}&nonce={nonce}"
    self.send_email('initial',
                    email=email,
                    link=link.format(**locals()),
                    username=self.username,
                    include_unsubscribe=False)


participants = db.all("""
    UPDATE participants p
       SET email = (e.email, false)
      FROM (
               SELECT DISTINCT ON (participant)
                      participant, email
                 FROM elsewhere
                WHERE email IS NOT NULL AND email <> ''
             ORDER BY participant, platform = 'github' DESC
           ) e
     WHERE e.participant = p.username
       AND p.email IS NULL
       AND NOT p.is_closed
       AND p.is_suspicious IS NOT true
       AND p.claimed_time IS NOT NULL;

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
