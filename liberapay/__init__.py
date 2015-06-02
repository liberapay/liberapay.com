from __future__ import print_function, unicode_literals

from . import constants


# canonizer
# =========
# This is an Aspen hook to ensure that requests are served on a certain root
# URL, even if multiple domains point to the application.

class X: pass
canonical_scheme = None
canonical_host = None

def canonize(request):
    """Enforce a certain scheme and hostname.
    """
    scheme = request.headers.get('X-Forwarded-Proto', 'http') # per Heroku
    host = request.headers['Host']
    bad_scheme = scheme != canonical_scheme
    bad_host = bool(canonical_host) and (host != canonical_host)
                # '' and False => ''
    if bad_scheme or bad_host:
        url = '%s://%s' % (canonical_scheme, canonical_host)
        if request.line.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            # Redirect to a particular path for idempotent methods.
            url += request.line.uri.path.raw
            if request.line.uri.querystring:
                url += '?' + request.line.uri.querystring.raw
        else:
            # For non-idempotent methods, redirect to homepage.
            url += '/'
        request.redirect(url)


def insert_constants():
    return {'constants': constants}
