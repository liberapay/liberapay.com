
class ElsewhereError(Exception):
    """Base class for elsewhere exceptions."""


class BadUserId(ElsewhereError):
    pass


class CantReadMembership(ElsewhereError):
    pass


class InvalidServerResponse(ElsewhereError):
    pass


class UserNotFound(ElsewhereError):
    pass
