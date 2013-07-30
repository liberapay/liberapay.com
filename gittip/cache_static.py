"""
Handles caching of static resources.
"""
import os
from calendar import timegm
from email.utils import parsedate
from wsgiref.handlers import format_date_time

from aspen import Response


def version_is_available(request):
    path = request.line.uri.path
    version = request.context['__version__']
    return ('version' in path) and path['version'] == version


def version_is_dash(request):
    return request.line.uri.path.get('version') == '-'


def get_last_modified(fs_path):
    return int(os.path.getctime(fs_path))


def inbound(request):
    """
    Checks the last modified time of a file against
    an If-Modified-Since header and responds with
    a 304 if appropriate.
    """
    uri = request.line.uri

    if not uri.startswith('/assets'):

        # Only apply to the assets/ directory.

        return request

    if not( version_is_available(request) or version_is_dash(request) ):

        # Prevent the possibility of serving one version of a file as if it
        # were another. You can work around it from your address bar using '-'
        # as the version: /assets/-/gittip.css.

        # If/when you do find yourself in a situation where you need to refresh
        # the cache with a specific version of this resource, one idea would be
        # to locally generate the version of the file you need and place it in
        # an explicit X.Y.Z directory that's sibling to %version.

        raise Response(404)

    ims = request.headers.get('If-Modified-Since')
    last_modified = get_last_modified(request.fs)

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

    version = request.context['__version__']
    response.headers['X-Gittip-Version'] = version

    if not uri.startswith('/assets'):
        return response

    response.headers.cookie.clear()

    if version_is_available(request):
        # This specific asset is versioned, so it's fine to cache this forever
        response.headers['Expires'] = 'Sun, 17 Jan 2038 19:14:07 GMT'
        response.headers['Cache-Control'] = 'public'
    else:
        # Asset is not versioned. Don't cache it.
        last_modified = get_last_modified(request.fs)
        response.headers['Last-Modified'] = format_date_time(last_modified)
        response.headers['Cache-Control'] = 'no-cache'
