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

class TooGreedy(Exception): pass
class NoSelfTipping(Exception): pass
class BadAmount(Exception): pass
