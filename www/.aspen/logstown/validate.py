"""Validators.

Given input, return a problem string, or the empty string if there are no problems.

"""
import re

from logstown.authentication import hash


# http://www.regular-expressions.info/email.html
EMAIL = re.compile('[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}')
DIGITS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
          'eight', 'nine']


def _plural(i):
    return "s" if i != 1 else ""

def email(email):
    problem = ""

    if not problem:
        if not email:
            problem = ("Um, did you enter an email address?")

    if not problem:
        if len(email) > 64:
            problem = ("Sorry, we won't take an email address longer than 64 "
                       "characters. Yours is %d." % len(email))

    if not problem:
        if EMAIL.match(email) is None:
            problem = "That doesn&rsquo;t look to me like an email address."

    return problem

def password(password, confirm):
    problem = ""

    if not problem:
        if len(password) < 6:
            short = 6 - len(password)
            problem = ("Sorry, your password must be at least six characters "
                       "long. You need %s more character%s.")
            problem %= DIGITS[short], _plural(short)

    if not problem:
        if password != confirm:
            problem = ("Sorry, the password and password confirmation "
                       "don&rsquo;t match.")

    return problem
