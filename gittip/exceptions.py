"""
This module contains exceptions shared across application code.
"""

from __future__ import print_function, unicode_literals


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


class ProblemChangingNumber(Exception):
    def __str__(self):
        return self.msg

class HasBigTips(ProblemChangingNumber):
    msg = "You receive tips too large for an individual. Please contact support@gittip.com."


class TooGreedy(Exception): pass
class NoSelfTipping(Exception): pass
class NoTippee(Exception): pass
class BadAmount(Exception): pass
class UserDoesntAcceptTips(Exception): pass

class FailedToReserveUsername(Exception): pass

class NegativeBalance(Exception):
    def __str__(self):
        return "Negative balance not allowed in this context."
