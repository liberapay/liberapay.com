
class ElsewhereError(Exception):
    """Base class for elsewhere exceptions."""


class CantReadMembership(ElsewhereError):
    pass


class UserNotFound(ElsewhereError):
    pass


class BadUserId(ElsewhereError):
    pass
