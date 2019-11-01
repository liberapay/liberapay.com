"""This module provides tools for Content Security Policies.
"""


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

    def allow(self, directive, value):
        d = dict(self.directives)
        old_value = d.get(directive)
        if old_value is None and directive in self.based_on_default_src:
            old_value = d.get(b'default-src')
        d[directive] = b'%s %s' % (old_value, value) if old_value else value
        return CSP(d)
