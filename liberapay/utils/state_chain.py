from __future__ import print_function, unicode_literals

import socket
import string

from six.moves.urllib.parse import urlsplit, urlunsplit, quote as urlquote

from aspen.http.request import Path
from aspen.request_processor.algorithm import dispatch_path_to_filesystem
from aspen.request_processor.dispatcher import NotFound, RedirectFromSlashless
from pando import Response
from pando.http.request import Line
from requests.exceptions import ConnectionError, Timeout

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
    is_callback = request.path.raw.startswith('/callbacks/')
    is_healthcheck = request.headers.get(b'User-Agent', b'').startswith(b'ELB-HealthChecker')
    if is_callback or is_healthcheck:
        # Don't redirect callbacks
        if request.path.raw[-1] == '/' or is_healthcheck:
            l = request.line
            scheme, netloc, path, query, fragment = urlsplit(l.uri)
            assert path[-1] == '/'  # sanity check
            path = '/callbacks/health.txt' if is_healthcheck else path[:-1]
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


def _dispatch_path_to_filesystem(website, request=None):
    """This wrapper function neutralizes some of Aspen's dispatch exceptions.

    - RedirectFromSlashless, always
    - NotFound, when it's due to an extra slash at the end of the path (i.e.
      dispatch `/foo/bar/` to `/foo/bar.spt`).
    """
    if request is None:
        return
    path = request.path
    qs = request.qs
    request_processor = website.request_processor
    try:
        return dispatch_path_to_filesystem(
            request_processor=request_processor, path=path, querystring=qs
        )
    except NotFound:
        raw_path = getattr(path, 'raw', '')
        if len(raw_path) < 3 or raw_path[-1] != '/' or raw_path[-2] == '/':
            raise
        path = Path(raw_path[:-1])
        if '.' in path.parts[-1]:
            # Don't dispatch `/foo.html/` to a `/foo.html` file
            raise
        r = dispatch_path_to_filesystem(
            request_processor=request_processor, path=path, querystring=qs
        )
        r['path'] = request.line.uri.path = path
        request.canonical_path = raw_path
        return r
    except RedirectFromSlashless as exception:
        path = urlquote(exception.message.encode('utf8'), string.punctuation)
        path = request.line.uri.path = Path(path)
        request.canonical_path = path.raw
        r = dispatch_path_to_filesystem(
            request_processor=request_processor, path=path, querystring=qs
        )
        r['path'] = path
        return r


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


def turn_socket_error_into_50X(website, exception, _=lambda a: a, response=None):
    # The mangopay module reraises exceptions and stores the original in `__cause__`.
    exception = getattr(exception, '__cause__', exception)
    if isinstance(exception, Timeout) or 'timeout' in str(exception).lower():
        response = response or Response()
        response.code = 504
    elif isinstance(exception, (socket.error, ConnectionError)):
        response = response or Response()
        response.code = 502
    else:
        return
    response.body = _(
        "Processing your request failed because our server was unable to communicate "
        "with a service located on another machine. This is a temporary issue, please "
        "try again later."
    )
    return {'response': response, 'exception': None}


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


def overwrite_status_code_of_gateway_errors(response):
    """This function changes 502 and 504 response codes to 500.

    Why? Because CloudFlare masks our error page if we return a 502 or 504:
    https://github.com/liberapay/liberapay.com/issues/592
    """
    if response.code in (502, 504):
        response.code = 500
