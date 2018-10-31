"""
Originally copied from Django
"""
from __future__ import unicode_literals

from binascii import b2a_base64
from os import urandom


def get_random_string(length=32, altchars=None):
    """
    Returns a securely generated random string.

    Args:
        length (int): the number of base64 characters to return
        altchars (bytes): optional replacement characters for `+` and `/`, e.g. b'-_'

    The default length (32) returns a value with 192 bits of entropy (log(64**32, 2)).
    """
    token = b2a_base64(urandom(length * 6 // 8 + 1))[:length]
    if altchars:
        token = token.replace(b'+', altchars[0]).replace(b'/', altchars[1])
    return token if str is bytes else token.decode('ascii')


def constant_time_compare(val1, val2):
    """
    Returns True if the two strings are equal, False otherwise.

    The time taken is independent of the number of characters that match.
    """
    if len(val1) != len(val2):
        return False
    result = 0
    if isinstance(val1, bytes) and bytes != str:
        for x, y in zip(val1, val2):
            result |= x ^ y
    else:
        for x, y in zip(val1, val2):
            result |= ord(x) ^ ord(y)
    return result == 0
