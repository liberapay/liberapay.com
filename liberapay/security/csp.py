"""This module provides tools for Content Security Policies.
"""

from typing import Tuple


class CSP(bytes):

    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/default-src
    based_on_default_src = set(b'''
        child-src connect-src font-src frame-src img-src manifest-src
        media-src object-src script-src style-src worker-src
    '''.split())

    def __new__(cls, x):
        if isinstance(x, dict):
            self = bytes.__new__(cls, b';'.join(b' '.join(t).rstrip() for t in x.items()) + b';')
            self.directives = dict(x)
        else:
            self = bytes.__new__(cls, x)
            self.directives = dict(
                (d.split(b' ', 1) + [b''])[:2] for d in self.split(b';') if d
            )
        return self


def csp_allow(response, *items: Tuple[bytes, bytes]) -> None:
    csp = response.headers[b'content-security-policy']
    d = csp.directives.copy()
    for directive, value in items:
        old_value = d.get(directive)
        if old_value is None and directive in csp.based_on_default_src:
            old_value = d.get(b'default-src')
        d[directive] = b'%s %s' % (old_value, value) if old_value else value
    response.headers[b'content-security-policy'] = CSP(d)


def csp_allow_stripe(response) -> None:
    # https://stripe.com/docs/security#content-security-policy
    csp_allow(
        response,
        (b'connect-src', b"api.stripe.com"),
        (b'frame-src', b"js.stripe.com hooks.stripe.com"),
        (b'script-src', b"js.stripe.com"),
    )
