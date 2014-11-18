"""
This is a one-off script to populate the new `emails` table using the addresses
we have in `participants` and `elsewhere`.
"""
from __future__ import division, print_function, unicode_literals

import uuid

from aspen.utils import utcnow
import gratipay.wireup

env = gratipay.wireup.env()
db = gratipay.wireup.db(env)
gratipay.wireup.mail(env)


INITIAL_EMAIL = dict(
    subject="Connect to {username} on Gratipay?",
    html="""\
<div style="text-align: center; font: normal 14px/21px Arial, sans-serif; color: #333;">
    We're working on adding email notifications to Gratipay (formerly Gittip)
    and we're sending this email to confirm that you (<b>{email}</b>)
    <br>
    are the owner of the <b><a href="https://gratipay.com/{username}">{username}</a></b>
    account on Gratipay. Sound familiar?
    <br>
    <br>
    <a href="{link}" style="color: #fff; text-decoration:none; display:inline-block; padding: 0 15px; background: #396; font: normal 14px/40px Arial, sans-serif; white-space: nowrap; border-radius: 3px">Yes, proceed!</a>

</div>
""",
    text="""\

We're working on adding email notifications to Gratipay (formerly Gittip)
and we're sending this email to confirm that you ({email}) are the owner
of the {username} account on Gratipay. Sound familiar? Follow this link
to finish connecting your email:

{link}

""",
)


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
    self.send_email(INITIAL_EMAIL,
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
