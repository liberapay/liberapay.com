from time import time

import pyotp


TOTP_DIGITS = 6
TOTP_PERIOD = 30


def generate_totp_secret():
    return pyotp.random_base32()


def normalize_totp_secret(secret):
    return ''.join(str(secret or '').upper().split())


def generate_totp_code(secret, now=None):
    if now is None:
        now = time()
    return pyotp.TOTP(normalize_totp_secret(secret)).at(now)


def verify_totp_code(secret, code, latest_counter=None, now=None, window=1):
    code = ''.join(str(code or '').split())
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False, None
    if now is None:
        now = time()
    totp = pyotp.TOTP(normalize_totp_secret(secret))
    counter = int(now // TOTP_PERIOD)
    for offset in range(-window, window + 1):
        candidate_counter = counter + offset
        if latest_counter is not None and candidate_counter <= latest_counter:
            continue
        try:
            candidate = totp.at(candidate_counter * TOTP_PERIOD)
        except (TypeError, ValueError):
            return False, None
        if pyotp.utils.strings_equal(candidate, code):
            return True, candidate_counter
    return False, None
