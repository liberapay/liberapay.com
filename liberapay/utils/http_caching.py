"""
Handles HTTP caching.
"""
from base64 import b64encode
from hashlib import md5

from aspen import Response


ETAGS = {}


def asset_etag(path):
    if path.endswith('.spt'):
        return ''
    if path in ETAGS:
        h = ETAGS[path]
    else:
        with open(path) as f:
            h = ETAGS[path] = b64encode(md5(f.read()).digest(), '-_').replace('=', '~')
    return h


# algorithm functions

def get_etag_for_file(dispatch_result):
    return {'etag': asset_etag(dispatch_result.match)}


def try_to_serve_304(dispatch_result, request, etag):
    """Try to serve a 304 for static resources.
    """
    if not etag:
        # This is a request for a dynamic resource.
        return

    qs_etag = request.line.uri.querystring.get('etag')
    if qs_etag and qs_etag != etag:
        # Don't serve one version of a file as if it were another.
        raise Response(410)

    headers_etag = request.headers.get('If-None-Match')
    if not headers_etag:
        # This client doesn't want a 304.
        return

    if headers_etag != etag:
        # Cache miss, the client sent an old or invalid etag.
        return

    # Huzzah!
    # =======
    # We can serve a 304! :D

    raise Response(304)


def add_caching_to_response(response, request=None, etag=None):
    """Set caching headers.
    """
    if not etag:
        # This is a dynamic resource, disable caching by default
        if 'Cache-Control' not in response.headers:
            response.headers['Cache-Control'] = 'no-cache'
        return

    assert request is not None  # sanity check

    if response.code not in (200, 304):
        return

    # https://developers.google.com/speed/docs/best-practices/caching
    response.headers['Etag'] = etag

    # Set CORS header for https://static.liberapay.com
    if 'Access-Control-Allow-Origin' not in response.headers:
        response.headers['Access-Control-Allow-Origin'] = 'https://liberapay.com'

    if request.line.uri.querystring.get('etag'):
        # We can cache "indefinitely" when the querystring contains the etag.
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    else:
        # Otherwise we cache for 5 seconds
        response.headers['Cache-Control'] = 'public, max-age=5'
