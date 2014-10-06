from __future__ import unicode_literals


# Header
# ======

HEADER = dict(
    html="""\
<div style="text-align: center; padding: 20px 0; margin: 0;">
    <img src="https://downloads.gratipay.com/email/gratipay.png" alt="Gratipay">
</div>
""",
    text="""\
Greetings, program!
""",
)


# Footer
# ======

FOOTER_NO_UNSUBSCRIBE = dict(
    html = """\

<div style="text-align: center; color: #999; padding: 21px 0 0;">
    <div style="font: normal 14px/21px Arial, sans-serif;">
        Something not right? Reply to this email for help.
    </div>
    <div style="font: normal 10px/21px Arial, sans-serif;">
        Sent by <a href="https://gratipay.com/" style="color: #999; text-decoration: underline;">Gratipay, LLC</a> | 716 Park Road, Ambridge, PA, 15003, USA
    </div>
</div>
    """,
    text = """\
Something not right? Reply to this email for help.

----

Sent by Gratipay, LLC, https://gratipay.com/
716 Park Road, Ambridge, PA, 15003, USA
""",
)

FOOTER = FOOTER_NO_UNSUBSCRIBE  # XXX Need to implement unsubscribe!


# Verification
# ============

VERIFICATION_EMAIL = dict(
    subject="Connect to {username} on Gratipay?",
    html="""\
<div style="text-align: center; font: normal 14px/21px Arial, sans-serif; color: #333;">
    We've received a request to connect <b>{email}</b>

    <br>

    to the <b><a href="https://gratipay.com/{username}">{username}</a></b>
    account on Gratipay. Sound familiar?

    <br><br>

    <a href="{link}" style="color: #fff; text-decoration:none; display:inline-block; padding: 0 15px; background: #396; font: normal 14px/40px Arial, sans-serif; white-space: nowrap; border-radius: 3px">Yes, proceed!</a>

</div>
""",
    text="""\

We've received a request to connect {email} to the {username}
account on Gratipay. Sound familiar? Follow this link to finish
connecting your email:

{link}

""",
)
