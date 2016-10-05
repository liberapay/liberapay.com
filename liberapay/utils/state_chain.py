from __future__ import print_function, unicode_literals

from six.moves.urllib.parse import urlsplit, urlunsplit

from pando import Response
from pando.http.request import Line

from .. import constants


def canonize(request, website):
    """Enforce a certain scheme and hostname.

    This is a Pando state chain function to ensure that requests are served on a
    certain root URL, even if multiple domains point to the application.
    """
    if request.path.raw.startswith('/callbacks/'):
        # Don't redirect callbacks
        if request.path.raw[-1] == '/':
            # Remove trailing slash
            l = request.line
            scheme, netloc, path, query, fragment = urlsplit(l.uri)
            assert path[-1] == '/'  # sanity check
            path = path[:-1]
            new_uri = urlunsplit((scheme, netloc, path, query, fragment))
            request.line = Line(l.method.raw, new_uri, l.version.raw)
        return
    scheme = request.headers.get(b'X-Forwarded-Proto', b'http')
    try:
        request.hostname = host = request.headers[b'Host'].decode('idna')
    except UnicodeDecodeError:
        request.hostname = host = ''
    canonical_host = website.canonical_host
    canonical_scheme = website.canonical_scheme
    bad_scheme = scheme.decode('ascii', 'replace') != canonical_scheme
    bad_host = False
    if canonical_host:
        if host == canonical_host:
            pass
        elif host.endswith('.'+canonical_host):
            subdomain = host[:-len(canonical_host)-1]
            if subdomain in website.locales:
                accept_langs = request.headers.get(b'Accept-Language', b'')
                accept_langs = subdomain.encode('idna') + b',' + accept_langs
                request.headers[b'Accept-Language'] = accept_langs
            else:
                bad_host = True
        else:
            bad_host = True
    if bad_scheme or bad_host:
        url = '%s://%s' % (canonical_scheme, canonical_host if bad_host else host)
        if request.line.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            # Redirect to a particular path for idempotent methods.
            url += request.line.uri.path.raw
            if request.line.uri.querystring:
                url += '?' + request.line.uri.querystring.raw
        else:
            # For non-idempotent methods, redirect to homepage.
            url += '/'
        website.redirect(url)


def insert_constants():
    return {'constants': constants}


def return_500_for_exception(website, exception, response=None):
    response = response or Response()
    response.code = 500
    if website.show_tracebacks:
        import traceback
        response.body = traceback.format_exc()
    else:
        response.body = (
            "Uh-oh, you've found a serious bug. Sorry for the inconvenience, "
            "we'll get it fixed ASAP."
        )
    return {'response': response, 'exception': None}
