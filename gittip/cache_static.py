"""
Handles caching of static resources.
"""
from os import path
from calendar import timegm
from email.utils import parsedate
from wsgiref.handlers import format_date_time

from aspen import Response


def inbound(request):
    """
    Checks the last modified time of a file against
    an If-Modified-Since header and responds with
    a 304 if appropriate.
    """
    uri = request.line.uri
    version = request.context['__version__']

    if not uri.startswith('/assets'):
        return request
    elif not version.endswith('dev') and version in uri:
        # These will be cached indefinitely in the outbound hook
        return request

    ims = request.headers.get('If-Modified-Since')
    last_modified = int(path.getctime(request.fs))

    if ims:
        ims = timegm(parsedate(ims))
        if ims >= last_modified:
            raise Response(304, headers={
                'Last-Modified': format_date_time(last_modified),
                'Cache-Control': 'no-cache'
            })


def outbound(response):
    request = response.request
    uri = request.line.uri
    if not uri.startswith('/assets'):
        return response

    version = request.context['__version__']
    if not version.endswith('dev') and version in uri:
        # This specific asset is versioned, so
        # it's fine to cache this forever
        response.headers['Expires'] = 'Sun, 17 Jan 2038 19:14:07 GMT'
        response.headers['Cache-Control'] = 'public'

    else:
        # Asset is not versioned or dev version is running.
        last_modified = int(path.getctime(request.fs))
        response.headers['Last-Modified'] = format_date_time(last_modified)
        response.headers['Cache-Control'] = 'no-cache'
