"""
Handles HTTP caching.
"""

import atexit
from hashlib import md5
import os
from os import stat
from tempfile import mkstemp

from aspen import resources, Response
from aspen.dispatcher import DispatchResult, DispatchStatus

from liberapay.utils import b64encode_s, find_files


ETAGS = {}


def compile_assets(website):
    cleanup = []
    for spt in find_files(website.www_root+'/assets/', '*.spt'):
        filepath = spt[:-4]  # /path/to/www/assets/foo.css
        if not os.path.exists(filepath):
            cleanup.append(filepath)
        dispatch_result = DispatchResult(DispatchStatus.okay, spt, {}, "Found.", {}, True)
        state = dict(dispatch_result=dispatch_result, response=Response())
        state['state'] = state
        content = resources.get(website, spt).respond(state).body
        if not isinstance(content, bytes):
            content = content.encode('utf8')
        tmpfd, tmpfpath = mkstemp(dir='.')
        os.write(tmpfd, content)
        os.close(tmpfd)
        os.rename(tmpfpath, filepath)
    if website.env.clean_assets:
        atexit.register(lambda: rm_f(*cleanup))


def rm_f(*paths):
    for path in paths:
        try:
            os.unlink(path)
        except:
            pass


def clean_assets(www_root):
    rm_f(*[spt[:-4] for spt in find_files(www_root+'/assets/', '*.spt')])


def asset_etag(path):
    if path.endswith('.spt'):
        return ''
    mtime = stat(path).st_mtime
    if path in ETAGS:
        h, cached_mtime = ETAGS[path]
        if cached_mtime == mtime:
            return h
    with open(path, 'rb') as f:
        h = b64encode_s(md5(f.read()).digest())
    ETAGS[path] = (h, mtime)
    return h


# algorithm functions

def get_etag_for_file(dispatch_result, website, state):
    try:
        return {'etag': asset_etag(dispatch_result.match)}
    except Exception as e:
        website.tell_sentry(e, state)
        return {'etag': None}


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

    if request.line.uri.querystring.get('etag'):
        # We can cache "indefinitely" when the querystring contains the etag.
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    else:
        # Otherwise we cache for 1 hour
        response.headers['Cache-Control'] = 'public, max-age=3600'
