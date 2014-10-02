from __future__ import unicode_literals


VERIFICATION_EMAIL = dict(
    subject="Welcome to Gratipay!",
    html="""
Welcome to Gratipay!
<br><br>
<a href="{link}">Verify your email address</a>.
""",
    text="""
Welcome to Gratipay! Verify your email address:

{link}
""",
)
