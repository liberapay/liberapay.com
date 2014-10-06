from __future__ import unicode_literals


VERIFICATION_EMAIL = dict(
    subject="Connect to {username} on Gratipay?",
    html="""\
<div style="text-align: center; font: normal 14px/21px Arial, sans-serif; color: #333;">

    <div style="padding: 40px 0 20px; margin: 0;">
        <img src="https://downloads.gratipay.com/email/gratipay.png">
    </div>

    We've received a request to connect <b>{email}</b>

    <br>

    to the <b><a href="https://gratipay.com/{username}">{username}</a></b>
    account on Gratipay. Sound familiar?

    <br><br>

    <a href="{link}" style="color: #fff; text-decoration:none; display:inline-block; padding: 0 15px; background: #396; font: normal 14px/40px Arial, sans-serif; white-space: nowrap; border-radius: 3px">Yes, proceed!</a>

    <br><br>

    <div style="color: #999;">Something not right? Reply to this email for help.</div>

</div>
""",
    text="""\
We've received a request to connect {email} to the
{username} account on Gratipay. Sound familiar? Follow this
link to finish making the connection:

{link}

Something not right? Reply to this email for help.

""",
)
