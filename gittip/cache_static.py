"""
Handles caching of static resources.
"""
import os
from calendar import timegm
from email.utils import parsedate
from wsgiref.handlers import format_date_time

from aspen import Response


def version_is_available(request):
    """Return a boolean, whether we have the version they asked for.
    """
    path = request.line.uri.path
    version = request.context['__version__']
    return path['version'] == version if 'version' in path else True


def version_is_dash(request):
    """Return a boolean, whether the version they asked for is -.
    """
    return request.line.uri.path.get('version') == '-'


def get_last_modified(fs_path):
    """Get the last modified time, as int, of the file pointed to by fs_path.
    """
    return int(os.path.getctime(fs_path))


def inbound(request):
    """Try to serve a 304 for resources under assets/.
    """
    uri = request.line.uri

    if not uri.startswith('/assets/'):

        # Only apply to the assets/ directory.

        return request

    if version_is_dash(request):

        # Special-case a version of '-' to never 304/404 here.

        return request

    if not version_is_available(request):

        # Don't serve one version of a file as if it were another.

        raise Response(404)

    ims = request.headers.get('If-Modified-Since')
    if not ims:

        # This client doesn't care about when the file was modified.

        return request

    if request.fs.endswith('.spt'):

        # This is a requests for a dynamic resource. Perhaps in the future
        # we'll delegate to such resources to compute a sensible Last-Modified
        # or E-Tag, but for now we punt. This is okay, because we expect to
        # put our dynamic assets behind a CDN in production.

        return request


    try:
        ims = timegm(parsedate(ims))
    except:

        # Malformed If-Modified-Since header. Proceed with the request.

        return request

    last_modified = get_last_modified(request.fs)
    if ims < last_modified:

        # The file has been modified since. Serve the whole thing.

        return request


    # Huzzah!
    # =======
    # We can serve a 304! :D

    response = Response(304)
    response.headers['Last-Modified'] = format_date_time(last_modified)
    response.headers['Cache-Control'] = 'no-cache'
    raise response


def outbound(response):
    """Set caching headers for resources under assets/.
    """
    request = response.request
    website = request.website
    uri = request.line.uri

    version = request.context['__version__']
    response.headers['X-Gittip-Version'] = version

    if not uri.startswith('/assets/'):
        return response

    response.headers.cookie.clear()

    if response.code == 304:
        return response

    if website.cache_static:

        # https://developers.google.com/speed/docs/best-practices/caching
        response.headers['Cache-Control'] = 'public'
        response.headers['Vary'] = 'accept-encoding'

        if 'version' in uri.path:
            # This specific asset is versioned, so it's fine to cache it.
            response.headers['Expires'] = 'Sun, 17 Jan 2038 19:14:07 GMT'
        else:
            # Asset is not versioned. Don't cache it, but set Last-Modified.
            last_modified = get_last_modified(request.fs)
            response.headers['Last-Modified'] = format_date_time(last_modified)
