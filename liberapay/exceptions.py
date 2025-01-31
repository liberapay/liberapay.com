from dependency_injection import resolve_dependencies
from pando import Response


class NextAction(Exception):
    def __init__(self, intent):
        self.__dict__.update(intent.next_action)
        self.client_secret = intent.client_secret


class Redirect(Exception):
    def __init__(self, url):
        self.url = url


class InvalidId(Response):

    def __init__(self, id, class_name):
        Response.__init__(self, 400, "Invalid %s ID: %r" % (class_name, id))

    def __str__(self):
        return self.body


class LazyResponse(Response):

    def __init__(self, code, lazy_body, **kw):
        Response.__init__(self, code, '', **kw)
        self.lazy_body = lazy_body

    def render_body(self, state):
        f = self.lazy_body
        self.body = f(*resolve_dependencies(f, state).as_args)
        return self.body

    def render_in_english(self):
        f = self.lazy_body
        fake_state = {}
        from liberapay.i18n.base import LOCALE_EN, add_helpers_to_context
        add_helpers_to_context(fake_state, LOCALE_EN)
        return f(*resolve_dependencies(f, fake_state).as_args)


class AuthRequired(LazyResponse):
    html_template = 'templates/exceptions/AuthRequired.html'
    navbar_sign_in = False

    def __init__(self):
        Response.__init__(self, 403, '')

    def lazy_body(self, _):
        return _("You need to sign in first")


class ClosedAccount(LazyResponse):
    html_template = 'templates/exceptions/ClosedAccount.html'

    def __init__(self, participant):
        Response.__init__(self, 410, '')
        self.closed_account = participant

    def lazy_body(self, _):
        return _("This account is closed")


class LoginRequired(LazyResponse):
    html_template = 'templates/exceptions/LoginRequired.html'

    def __init__(self):
        Response.__init__(self, 403, '')

    def lazy_body(self, _):
        return _("Authentication required")


class AccountIsPasswordless(LoginRequired):
    pass


class NeedDatabase(LazyResponse):
    html_template = 'templates/exceptions/NeedDatabase.html'

    def __init__(self):
        Response.__init__(self, 503, '')

    def lazy_body(self, _):
        return _("We're unable to process your request right now, sorry.")


class LazyResponseXXX(LazyResponse):

    def __init__(self, *args, headers=None):
        Response.__init__(self, self.code, '', headers=headers)
        self.lazy_body = self.msg
        self.args = args

    __str__ = Exception.__str__


class LazyResponse400(LazyResponseXXX):
    code = 400


class UsernameError(LazyResponse400):

    def __init__(self, username):
        super().__init__()
        self.username = username

    def __str__(self):
        return self.username


class UsernameIsEmpty(UsernameError):
    def msg(self, _):
        return _("You need to provide a username!")


class UsernameTooLong(UsernameError):
    def msg(self, _):
        return _("The username '{0}' is too long.", self.username)


class UsernameContainsInvalidCharacters(UsernameError):
    def msg(self, _):
        return _("The username '{0}' contains invalid characters.", self.username)


class UsernameIsPurelyNumerical(UsernameError):
    def msg(self, _):
        return _("The username '{0}' is purely numerical. This isn't allowed.")


class UsernameIsRestricted(UsernameError):
    def msg(self, _):
        return _("The username '{0}' is restricted.", self.username)


class UsernameAlreadyTaken(UsernameError):
    def msg(self, _):
        return _("The username '{0}' is already taken.", self.username)


class UsernameBeginsWithRestrictedCharacter(UsernameError):
    def msg(self, _):
        return _("The username '{0}' begins with a restricted character.", self.username)


class UsernameEndsWithForbiddenSuffix(UsernameError):

    def __init__(self, username, suffix):
        super().__init__(username)
        self.suffix = suffix

    def msg(self, _):
        return _("The username '{0}' ends with the forbidden suffix '{1}'.",
                 self.username, self.suffix)


class TooManyUsernameChanges(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "You've already changed your username many times recently, please "
            "retry later (e.g. in a week) or contact support@liberapay.com."
        )


class ValueTooLong(LazyResponse400):
    def msg(self, _):
        return _("The value '{0}' is too long.", self.args[0])


class ValueContainsForbiddenCharacters(LazyResponse400):
    def msg(self, _, locale):
        return _(
            "The value '{0}' contains the following forbidden characters: {1}.",
            self.args[0], ["'%s'" % c for c in self.args[1]]
        )


class EmailAddressError(LazyResponse400):
    bypass_allowed = False
    html_template = 'templates/exceptions/EmailAddressError.html'

    def __init__(self, address, exception_or_message=None):
        super().__init__()
        self.email_address = address
        self.exception_or_message = exception_or_message

    def __str__(self):
        return "%s (%r)" % (self.email_address, self.exception_or_message)


class EmailAlreadyTaken(EmailAddressError):
    code = 409
    def msg(self, _):
        return _("{0} is already connected to a different Liberapay account.", self.email_address)


class CannotRemovePrimaryEmail(LazyResponseXXX):
    code = 403
    def msg(self, _):
        return _("You cannot remove your primary email address.")


class EmailNotVerified(EmailAddressError):
    def msg(self, _):
        return _("The email address '{0}' is not verified.", self.email_address)


class TooManyEmailAddresses(LazyResponseXXX):
    code = 403
    def msg(self, _):
        return _("You've reached the maximum number of email addresses we allow.")


class BadEmailAddress(EmailAddressError):
    def msg(self, _):
        return _("'{0}' is not a valid email address.", self.email_address)


class InvalidEmailDomain(EmailAddressError):

    def __init__(self, email_address, domain, exception):
        super().__init__(email_address, exception)
        self.invalid_domain = domain

    def msg(self, _):
        return _("{0} is not a valid domain name.", repr(self.invalid_domain))


class EmailDomainUnresolvable(EmailAddressError):
    def msg(self, _):
        return _(
            "Our attempt to resolve the domain {domain_name} failed "
            "(error message: “{error_message}”).",
            domain_name=self.email_address.domain,
            error_message=str(self.exception_or_message),
        )


class BrokenEmailDomain(EmailAddressError):
    bypass_allowed = True

    def msg(self, _):
        return _(
            "Our attempt to establish a connection with the {domain_name} email "
            "server failed (error message: “{error_message}”).",
            domain_name=self.email_address.domain,
            error_message=str(self.exception_or_message),
        )


class NonEmailDomain(EmailAddressError):
    def msg(self, _):
        return _(
            "'{domain_name}' is not a valid email domain.",
            domain_name=self.email_address.domain
        )


class EmailAddressRejected(EmailAddressError):

    def __init__(self, address, error_msg, mx_ip_address):
        super().__init__(address, error_msg)
        self.mx_ip_address = mx_ip_address

    def msg(self, _):
        return _(
            "The email address {email_address} doesn't seem to exist. The {domain} "
            "email server at IP address {ip_address} rejected it with the error "
            "message “{error_message}”.",
            email_address="<{}>".format(self.email_address),
            domain=self.email_address.rsplit('@', 1)[-1],
            ip_address=self.mx_ip_address,
            error_message=str(self.exception_or_message),
        )


class EmailAddressIsBlacklisted(LazyResponse400):
    html_template = 'templates/exceptions/EmailAddressIsBlacklisted.html'

    def __init__(self, email_address, reason, ts, details, ses_data=None):
        Response.__init__(self, 400, '')
        from liberapay.utils.emails import EmailError
        self.email_error = EmailError(email_address, reason, ts, details, ses_data)

    def lazy_body(self, _):
        from liberapay.i18n.base import to_age
        error = self.email_error
        if error.reason == 'bounce':
            return _(
                "The email address {email_address} is blacklisted because an "
                "attempt to send a message to it failed {timespan_ago}.",
                email_address=error.email_address, timespan_ago=to_age(error.ts)
            )
        else:
            return _(
                "The email address {email_address} is blacklisted because of a "
                "complaint received {timespan_ago}. Please send an email "
                "from that address to support@liberapay.com if you want us to "
                "remove it from the blacklist.",
                email_address=error.email_address, timespan_ago=to_age(error.ts)
            )


class EmailDomainIsBlacklisted(LazyResponse400):
    def msg(self, _):
        from liberapay.i18n.base import to_age
        domain, reason, ts, details = self.args
        if reason == 'bounce':
            return _(
                "The email domain {domain} was blacklisted on {date} because "
                "it was bouncing back all messages. Please contact us if that "
                "is no longer true and you want us to remove this domain from "
                "the blacklist.",
                domain=domain, date=ts.date()
            )
        elif reason == 'complaint':
            return _(
                "The email domain {domain} is blacklisted because of a complaint "
                "received {timespan_ago}. Please contact us if this domain is "
                "yours and you want us to remove it from the blacklist.",
                domain=domain, timespan_ago=to_age(ts)
            )
        elif reason == 'throwaway':
            return _(
                "The email domain {domain} was blacklisted on {date} because "
                "it provided disposable addresses. Please contact us if that "
                "is no longer true and you want us to remove this domain from "
                "the blacklist.",
                domain=domain, date=ts.date()
            )
        else:
            return _(
                "The email domain {domain} is blacklisted. Please contact us if "
                "you want us to remove it from the blacklist.",
                domain=domain
            )


class EmailAlreadyAttachedToSelf(EmailAddressError):
    code = 409
    def msg(self, _):
        return _("The email address {0} is already connected to your account.", self.email_address)


class VerificationEmailAlreadySent(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "A verification email has already been sent to {email_address} recently.",
            email_address=self.args[0]
        )


class TooManyEmailVerifications(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "You are not allowed to add another email address right now, please "
            "try again in a few days."
        )


class TooManyLogInAttempts(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "There have been too many attempts to log in from your IP address or country "
            "recently. Please try again in an hour and email support@liberapay.com if "
            "the problem persists."
        )


class TooManyLoginEmails(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "You have consumed your quota of email logins, please try again tomorrow, "
            "or contact support@liberapay.com."
        )


class TooManyPasswordLogins(LazyResponse):
    html_template = 'templates/exceptions/TooManyPasswordLogins.html'

    def __init__(self, participant_id):
        Response.__init__(self, 429, '')

    def lazy_body(self, _):
        return _(
            "There have been too many attempts to log in to this account recently, "
            "please try again in a few hours or log in via email."
        )


class TooManySignUps(LazyResponseXXX):
    code = 503
    def msg(self, _):
        return _(
            "Too many accounts have been created recently. This either means that "
            "a lot of people are trying to join Liberapay today, or that an attacker "
            "is trying to overload our system. As a result we have to ask you to come "
            "back later (e.g. in a few hours), or send an email to support@liberapay.com. "
            "We apologize for the inconvenience."
        )


class TooManyTeamsCreated(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "You've already created several teams recently, please come back in a week."
        )


class BadPasswordSize(LazyResponse400):
    def msg(self, _):
        from .constants import PASSWORD_MIN_SIZE, PASSWORD_MAX_SIZE
        return _("The password must be at least {0} and at most {1} characters long.",
                 PASSWORD_MIN_SIZE, PASSWORD_MAX_SIZE)


class NoSelfTipping(LazyResponse400):
    def msg(self, _):
        return _("You can't donate to yourself.")


class NoTippee(LazyResponse400):
    def msg(self, _):
        return _("There is no user named {0}.", *self.args)


_ = lambda a: a
BAD_AMOUNT_MESSAGES = {
    'weekly': _("'{0}' is not a valid weekly donation amount (min={1}, max={2})"),
    'monthly': _("'{0}' is not a valid monthly donation amount (min={1}, max={2})"),
    'yearly': _("'{0}' is not a valid yearly donation amount (min={1}, max={2})"),
}
del _

class BadAmount(LazyResponse400):
    def msg(self, _):
        amount, period, limits = self.args
        return _(BAD_AMOUNT_MESSAGES[period], amount, *limits)


class UserDoesntAcceptTips(LazyResponseXXX):
    code = 403
    def msg(self, _):
        return _("The user {0} doesn't accept donations.", *self.args)


class BadDonationCurrency(LazyResponseXXX):
    code = 403
    def msg(self, _, locale):
        tippee, rejected_currency = self.args
        return _(
            "{username} doesn't accept donations in {rejected_currency}.",
            username=tippee.username,
            rejected_currency=locale.Currency(rejected_currency),
        )


class UnacceptedDonationVisibility(LazyResponseXXX):
    code = 403
    def msg(self, _):
        tippee, visibility = self.args
        return _(
            "{username} no longer accepts secret donations.", username=tippee.username,
        ) if visibility == 1 else _(
            "{username} no longer accepts private donations.", username=tippee.username,
        ) if visibility == 2 else _(
            "{username} no longer accepts public donations.", username=tippee.username,
        )


class UnexpectedCurrency(LazyResponse400):

    def __init__(self, unexpected_amount, expected_currency):
        super().__init__()
        self.unexpected_amount = unexpected_amount
        self.expected_currency = expected_currency

    def msg(self, _):
        return _(
            "The amount {money_amount} isn't in the expected currency ({expected_currency}).",
            money_amount=self.unexpected_amount, expected_currency=self.expected_currency,
        )


class NonexistingElsewhere(LazyResponse400):
    def msg(self, _):
        return _("It seems you're trying to delete something that doesn't exist.")


class InvalidNumber(LazyResponse400):
    def msg(self, _):
        return _('"{0}" is not a valid number.', *self.args)


class AmbiguousNumber(LazyResponse400):
    html_template = 'templates/exceptions/AmbiguousNumber.html'

    def __init__(self, ambiguous_string, suggestions):
        Response.__init__(self, 400, '')
        self.ambiguous_string = ambiguous_string
        self.suggestions = suggestions

    def lazy_body(self, _, locale):
        if self.suggestions:
            return _(
                '"{0}" doesn\'t match the expected number format. Perhaps you '
                'meant {list_of_suggestions}?',
                self.ambiguous_string,
                list_of_suggestions=locale.List(self.suggestions, 'or')
            )
        else:
            return _('"{0}" is not a properly formatted number.', self.ambiguous_string)


class CommunityAlreadyExists(LazyResponse400):
    def msg(self, _):
        return _('The "{0}" community already exists.', *self.args)


class InvalidCommunityName(LazyResponse400):
    def msg(self, _):
        return _('"{0}" is not a valid community name.', *self.args)


class AccountSuspended(LazyResponseXXX):
    code = 403
    def msg(self, _):
        return _(
            "You are not allowed to do this because your account is currently "
            "suspended."
        )


class EmailRequired(LazyResponseXXX):
    code = 403
    def msg(self, _):
        return _("Your account lacks a valid email address, please add one.")


class RecipientAccountSuspended(LazyResponseXXX):
    code = 403
    def msg(self, _):
        return _(
            "This payment cannot be processed because the account of the "
            "recipient is currently suspended."
        )


class MissingPaymentAccount(LazyResponseXXX):
    code = 400
    def msg(self, _):
        return _(
            "Your donation to {recipient} cannot be processed right now because the "
            "account of the beneficiary isn't ready to receive money.",
            recipient=self.args[0].username
        )


class ProhibitedSourceCountry(LazyResponseXXX):
    code = 403

    def __init__(self, recipient, country):
        super().__init__()
        self.recipient = recipient
        self.country = country

    def msg(self, _, locale):
        return _(
            "{username} does not accept donations from {country}.",
            username=self.recipient.username, country=locale.Country(self.country)
        )


class UnableToDeterminePayerCountry(LazyResponseXXX):
    code = 500
    def msg(self, _):
        return _(
            "The processing of your payment has failed because our software was "
            "unable to determine which country the money would come from. This "
            "isn't supposed to happen."
        )


class TooManyCurrencyChanges(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "You've already changed your main currency recently, please retry "
            "later (e.g. in a week) or contact support@liberapay.com."
        )


class TooManyAttempts(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "There have been too many attempts to perform this action recently, please "
            "retry later (e.g. in a week) or contact support@liberapay.com if you "
            "require assistance."
        )


class TooManyRequests(LazyResponseXXX):
    code = 429
    def msg(self, _):
        return _(
            "You're sending requests at an unusually fast pace. Please retry in a few "
            "seconds, and contact support@liberapay.com if the problem persists."
        )


class TooManyAdminActions(Response):
    def __init__(self, *args, **kw):
        Response.__init__(self, 429, (
            "You have consumed your quota of admin actions. This isn't supposed "
            "to happen."
        ))


class UnableToSendEmail(LazyResponseXXX):
    code = 500
    def msg(self, _):
        return _(
            "The attempt to send an email to {email_address} failed. Please "
            "check that the address is valid and retry. If the problem persists, "
            "please contact support@liberapay.com.", email_address=self.args[0]
        )


class PayinMethodIsUnavailable(LazyResponseXXX):
    code = 503
    def msg(self, _):
        return _("This payment method is currently unavailable. We apologize for the inconvenience.")


class PaymentError(LazyResponseXXX):
    code = 500
    def msg(self, _):
        return _(
            "The payment processor {name} returned an error. Please try again "
            "and contact support@liberapay.com if the problem persists.",
            name=self.args[0]
        )


class DuplicateNotification(Exception):
    pass
