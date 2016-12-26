from __future__ import print_function, unicode_literals

from six.moves.urllib.parse import urlsplit, urlunsplit

from pando import Response
from pando.http.request import Line

from .. import constants
from ..exceptions import LazyResponse


def create_response_object(request, website):
    response = Response()
    response.request = request
    response.website = website
    return {'response': response}


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
        response = Response()
        response.headers[b'Cache-Control'] = b'public, max-age=86400'
        response.redirect(url)


def insert_constants():
    return {'constants': constants}


def merge_exception_into_response(state, exception, response=None):
    if response is None or not isinstance(exception, Response):
        return
    # clear the exception
    state['exception'] = None
    # set debug info
    exception.set_whence_raised()
    # render response if it's lazy
    if isinstance(exception, LazyResponse):
        exception.render_body(state)
        exception.__dict__.pop('lazy_body', None)
    # there's nothing else to do if the exception is the response
    if exception is response:
        return
    # merge cookies
    response.headers.cookie.update(exception.headers.cookie)
    # merge headers
    for k, values in exception.__dict__.pop('headers').items():
        for v in values:
            response.headers.add(k, v)
    # copy the rest
    response.__dict__.update(exception.__dict__)


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
