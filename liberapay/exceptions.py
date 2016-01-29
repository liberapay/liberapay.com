from __future__ import print_function, unicode_literals

from aspen import Response
from dependency_injection import resolve_dependencies

from .constants import MAX_TIP, MIN_TIP, PASSWORD_MIN_SIZE, PASSWORD_MAX_SIZE


class LazyResponse(Response):

    def __init__(self, code, lazy_body, **kw):
        Response.__init__(self, code, '', **kw)
        self.lazy_body = lazy_body

    def render_body(self, state):
        f = self.lazy_body
        self.body = f(*resolve_dependencies(f, state).as_args)


class AuthRequired(LazyResponse):
    show_sign_in_form = True

    def __init__(self, *args, **kw):
        Response.__init__(self, 403, '', **kw)

    def lazy_body(self, _):
        return _("You need to sign in first")


class LazyResponse400(LazyResponse):

    def __init__(self, *args, **kw):
        Response.__init__(self, 400, '', **kw)
        self.lazy_body = self.msg
        self.args = args


class ProblemChangingUsername(LazyResponse400): pass

class UsernameIsEmpty(ProblemChangingUsername):
    def msg(self, _):
        return _("You need to provide a username!")

class UsernameTooLong(ProblemChangingUsername):
    def msg(self, _):
        return _("The username '{0}' is too long.", *self.args)

class UsernameContainsInvalidCharacters(ProblemChangingUsername):
    def msg(self, _):
        return _("The username '{0}' contains invalid characters.", *self.args)

class UsernameIsRestricted(ProblemChangingUsername):
    def msg(self, _):
        return _("The username '{0}' is restricted.", *self.args)

class UsernameAlreadyTaken(ProblemChangingUsername):
    def msg(self, _):
        return _("The username '{0}' is already taken.", *self.args)


class ProblemChangingEmail(LazyResponse400): pass

class EmailAlreadyTaken(ProblemChangingEmail):
    def msg(self, _):
        return _("{0} is already connected to a different Liberapay account.", *self.args)

class CannotRemovePrimaryEmail(ProblemChangingEmail):
    def msg(self, _):
        return _("You cannot remove your primary email address.")

class EmailNotVerified(ProblemChangingEmail):
    def msg(self, _):
        return _("The email address '{0}' is not verified.", *self.args)

class TooManyEmailAddresses(ProblemChangingEmail):
    def msg(self, _):
        return _("You've reached the maximum number of email addresses we allow.")

class BadEmailAddress(ProblemChangingEmail):
    def msg(self, _):
        return _("'{0}' is not a valid email address.", *self.args)


class BadPasswordSize(LazyResponse400):
    def msg(self, _):
        return _("The password must be at least {0} and at most {1} characters long.",
                 PASSWORD_MIN_SIZE, PASSWORD_MAX_SIZE)


class NoSelfTipping(LazyResponse400):
    def msg(self, _):
        return _("You can't donate to yourself.")

class NoTippee(LazyResponse400):
    def msg(self, _):
        return _("There is no user named {0}.", *self.args)

class BadAmount(LazyResponse400):
    def msg(self, _):
        return _("'{0}' is not a valid donation amount (min={1}, max={2})",
                 self.args[0], MIN_TIP, MAX_TIP)

class UserDoesntAcceptTips(LazyResponse400):
    def msg(self, _):
        return _("The user {0} doesn't accept donations.", *self.args)


class NonexistingElsewhere(LazyResponse400):
    def msg(self, _):
        return _("It seems you're trying to delete something that doesn't exist.")


class NegativeBalance(LazyResponse400):
    def msg(self, _):
        return _("There isn't enough money in your wallet.")


class NotEnoughWithdrawableMoney(LazyResponse400):
    def msg(self, _):
        return _("You can't withdraw more than {0} at this time.", *self.args)


class UserIsSuspicious(Exception): pass


class TransactionFeeTooHigh(LazyResponse400):
    def msg(self, _):
        return _("The transaction fee would be more than 10%.")


class InvalidNumber(LazyResponse400):
    def msg(self, _):
        return _('"{0}" is not a valid number.', *self.args)


class CommunityAlreadyExists(LazyResponse400):
    def msg(self, _):
        return _('The "{0}" community already exists.', *self.args)


class InvalidCommunityName(LazyResponse400):
    def msg(self, _):
        return _('"{0}" is not a valid community name.', *self.args)
