"""
This module contains exceptions shared across application code.
"""

from __future__ import print_function, unicode_literals

from aspen import Response


class ProblemChangingUsername(Exception):
    def __str__(self):
        return self.msg.format(self.args[0])

class UsernameIsEmpty(ProblemChangingUsername):
    msg = "You need to provide a username!"

class UsernameTooLong(ProblemChangingUsername):
    msg = "The username '{}' is too long."

class UsernameContainsInvalidCharacters(ProblemChangingUsername):
    msg = "The username '{}' contains invalid characters."

class UsernameIsRestricted(ProblemChangingUsername):
    msg = "The username '{}' is restricted."

class UsernameAlreadyTaken(ProblemChangingUsername):
    msg = "The username '{}' is already taken."


class ProblemChangingEmail(Response):
    def __init__(self, *args):
        Response.__init__(self, 400, self.msg.format(*args))

class EmailAlreadyTaken(ProblemChangingEmail):
    msg = "{} is already connected to a different Gratipay account."

class CannotRemovePrimaryEmail(ProblemChangingEmail):
    msg = "You cannot remove your primary email address."

class EmailNotVerified(ProblemChangingEmail):
    msg = "The email address '{}' is not verified."

class TooManyEmailAddresses(ProblemChangingEmail):
    msg = "You've reached the maximum number of email addresses we allow."


class ProblemChangingNumber(Exception):
    def __str__(self):
        return self.msg

class HasBigTips(ProblemChangingNumber):
    msg = "You receive tips too large for an individual. Please contact support@gratipay.com."


class TooGreedy(Exception): pass
class NoSelfTipping(Exception): pass
class NoTippee(Exception): pass
class BadAmount(Exception): pass
class UserDoesntAcceptTips(Exception): pass

class FailedToReserveUsername(Exception): pass

class NegativeBalance(Exception):
    def __str__(self):
        return "Negative balance not allowed in this context."

class NotWhitelisted(Exception): pass
class NoBalancedCustomerHref(Exception): pass
