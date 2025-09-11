from urllib.parse import quote as urlquote

from pando import Response
import pando.state_chain
from requests.exceptions import ConnectionError, Timeout

from .. import constants
from ..i18n.base import LOCALES_DEFAULT_MAP
from ..exceptions import LazyResponse, TooManyRequests


def add_state_to_context(state, website):
    website.state.set(state)


def attach_environ_to_request(environ, request):
    request.source_country = request.headers.get(b'Cf-Ipcountry', b'').decode() or None
    request.environ = environ
    try:
        request.hostname = request.headers[b'Host'].decode('idna')
    except UnicodeDecodeError:
        request.hostname = ''
    request.subdomain = None
    request.save_data = request.headers.get(b'Save-Data') == b'on'


def create_response_object(request, website):
    response = Response()
    response.request = request
    response.website = website
    return {'response': response}


def raise_response_to_OPTIONS_request(request, response):
    """Return a 204 (No Content) for all OPTIONS requests.

    Ideally a response to an OPTIONS request for a specific URL includes an
    `Allow` header listing all the valid request methods for that URL, but we
    currently don't have a simple way of getting that list.

    https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods/OPTIONS
    """
    if request and request.line.method == b"OPTIONS":
        response.code = 204
        raise response


def canonize(request, response, website):
    """Enforce a certain scheme and hostname.

    This is a Pando state chain function to ensure that requests are served on a
    certain root URL, even if multiple domains point to the application.
    """
    if request.path.raw.startswith('/callbacks/'):
        # Don't redirect callbacks
        return
    canonical_host = website.canonical_host
    canonical_scheme = website.canonical_scheme
    scheme = request.headers.get(b'X-Forwarded-Proto', b'http')
    scheme_is_canonical = scheme.decode('ascii', 'replace') == canonical_scheme
    host = request.hostname
    host_is_canonical = True
    if canonical_host and host != canonical_host:
        if host.endswith(website.dot_canonical_host):
            request.subdomain = host[:-len(website.dot_canonical_host)]
            host_is_canonical = (
                request.subdomain in website.locales or
                request.subdomain in LOCALES_DEFAULT_MAP
            )
        else:
            host_is_canonical = False
    if not (scheme_is_canonical and host_is_canonical):
        url = f'{canonical_scheme}://{host if host_is_canonical else canonical_host}'
        if request.method in constants.SAFE_METHODS:
            # For idempotent methods, preserve the path and querystring.
            url += request.line.uri.path.decoded
            if request.line.uri.querystring:
                url += '?' + request.line.uri.querystring.decoded
            # Allow caching the redirect for an hour when in production.
            if website.env.instance_type == 'production':
                response.headers[b'Cache-Control'] = b'public, max-age=3600'
        else:
            # For non-idempotent methods, redirect to homepage.
            url += '/'
        raise response.redirect(url)


def drop_accept_all_header(accept_header=None):
    # This is a temporary workaround for a shortcoming in Aspen
    if accept_header == '*/*':
        return {'accept_header': None}


def detect_obsolete_browsers(request, response, state):
    """Respond with a warning message if the user agent seems to be obsolete.
    """
    if b'MSIE' in request.headers.get(b'User-Agent', b''):
        if state.get('etag'):
            return
        if request.cookies.get('obsolete_browser_warning') == 'ignore':
            return
        if request.method == 'POST':
            try:
                action = request.body.get('obsolete-browser-warning')
            except Exception:
                pass
            else:
                if action == 'ignore':
                    response.headers.cookie['obsolete_browser_warning'] = 'ignore'
                    return
        raise response.render('simplates/obsolete-browser-warning.spt', state)


def insert_constants():
    return {'constants': constants}


def enforce_rate_limits(request, user, website, etag=None):
    if request.method in constants.SAFE_METHODS:
        if request.qs:
            if etag:
                # Don't count requests for static assets
                return
            request_type = 'http-query'
        else:
            return
    else:
        request_type = 'http-unsafe'
    if user.id:
        website.db.hit_rate_limit(request_type + '.user', user.id, TooManyRequests)
    else:
        website.db.hit_rate_limit(request_type + '.ip-addr', request.source, TooManyRequests)


def set_output_to_None(state):
    # This is a temporary workaround for a shortcoming in Pando 0.47
    state.setdefault('output', None)


def add_content_disposition_header(request, response):
    """Tell the browser if the response is meant to be saved into a file.

    https://tools.ietf.org/html/rfc6266 and https://tools.ietf.org/html/rfc8187
    """
    save_as = request.qs.get('save_as')
    if save_as:
        save_as = urlquote(save_as, encoding='utf8').encode('ascii')
        response.headers[b'Content-Disposition'] = b"attachment; filename*=UTF-8''" + save_as


def merge_responses(state, exception, website, response=None):
    """Merge the initial Response object with the one raised later in the chain.
    """
    if not isinstance(exception, Response):
        return
    # log the exception
    state.update(website.tell_sentry(exception))
    # clear the exception
    state['exception'] = None
    # set debug info
    exception.set_whence_raised()
    # render response if it's lazy
    if isinstance(exception, LazyResponse):
        try:
            exception.render_body(state)
        except Exception:
            pass
    # there's nothing else to do if the exception is the response
    if exception is response:
        return
    # set response
    state['response'] = exception
    # there's nothing to merge if there's no prior Response object in the state
    if response is None:
        return
    # merge cookies
    for k, v in response.headers.cookie.items():
        exception.headers.cookie.setdefault(k, v)
    # merge headers
    for k, values in response.__dict__.pop('headers').items():
        exception.headers.setdefault(k, values)
    # copy the rest
    if hasattr(response, '__dict__'):
        for k, v in response.__dict__.items():
            exception.__dict__.setdefault(k, v)


def turn_socket_error_into_50X(website, state, exception, _=str.format, response=None):
    """Catch network errors and replace them with a 502 or 504 response.

    Because network exceptions are often caught and wrapped by libraries, this
    function recursively looks at the standard `__cause__` and `__context__`
    attributes of exceptions in order to find the initial error.

    https://docs.python.org/3/reference/simple_stmts.html#the-raise-statement
    https://stackoverflow.com/a/11235957/2729778
    """
    for i in range(100):
        if isinstance(exception, Timeout) or 'timeout' in str(exception).lower():
            response = response or Response()
            response.code = 504
            break
        elif isinstance(exception, (OSError, ConnectionError)):
            response = response or Response()
            response.code = 502
            break
        elif getattr(exception, '__cause__', None):
            exception = exception.__cause__
        elif getattr(exception, '__context__', None):
            exception = exception.__context__
        else:
            return
    # log the exception
    website.tell_sentry(exception, level='warning')
    # show a proper error message
    response.body = _(
        "Processing your request failed because our server was unable to communicate "
        "with a service located on another machine. This is a temporary issue, please "
        "try again later."
    )
    return {'response': response, 'exception': None}


def get_response_for_exception(state, website, exception, response=None):
    if isinstance(exception, Response):
        return merge_responses(state, exception, website, response)
    else:
        response = response or Response(500)
        if response.code < 400:
            response.code = 500
        response.__cause__ = exception
        return {'response': response, 'exception': None}


def delegate_error_to_simplate(website, state, response, request=None, resource=None):
    """
    Wrap Pando's function to avoid dispatching to `error.spt` if the response is
    already a complete error page.
    """
    if b'Content-Type' in response.headers:
        return  # this response is already completely rendered
    return pando.state_chain.delegate_error_to_simplate(
        website, state, response, request, resource
    )


def bypass_csp_for_form_redirects(response, state, website, request=None):
    if request is None:
        return
    # https://github.com/liberapay/liberapay.com/issues/952
    if response.code == 302:
        target = response.headers[b'Location']
        is_internal = (
            target[:1] in (b'/', b'.') or
            target.startswith(b'%s://%s/' % (
                website.canonical_scheme.encode('ascii'), request.headers[b'Host']
            ))
        )
        if is_internal:
            # Not an external redirect
            return
        response.code = 200
        url = response.headers.pop(b'Location').decode('ascii')
        try:
            response.refresh(state, interval=0, url=url)
        except Response:
            pass


def overwrite_status_code_of_gateway_errors(response):
    """This function changes 502 and 504 response codes to 500.

    Why? Because CloudFlare masks our error page if we return a 502 or 504:
    https://github.com/liberapay/liberapay.com/issues/592
    """
    if response.code in (502, 504):
        response.code = 500


def no_response_body_for_HEAD_requests(response, request=None, exception=None):
    """This function ensures that we only return headers in response to a HEAD request.

    Gunicorn, Pando and Aspen currently all fail to prevent a body from being sent
    in a response to a HEAD request, even though the HTTP spec clearly states that
    a “server MUST NOT send a message body in the response [to a HEAD request]”:
    https://datatracker.ietf.org/doc/html/rfc7231#section-4.3.2
    """
    if request and request.method == 'HEAD' and response.body:
        response.body = b''


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
    response.headers[b'Cache-Control'] = b'no-cache'
    response.headers[b'Content-Type'] = b'text/plain'
    return {'response': response, 'exception': None}
