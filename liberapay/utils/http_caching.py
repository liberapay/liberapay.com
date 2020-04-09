"""
Handles HTTP caching.
"""

import atexit
from hashlib import md5
import os
from tempfile import mkstemp

from aspen.request_processor.dispatcher import DispatchResult, DispatchStatus
from pando import Response

from liberapay.utils import b64encode_s, find_files


ETAGS = {}


def compile_assets(website):
    cleanup = []
    for spt in find_files(website.www_root+'/assets/', '*.spt'):
        filepath = spt[:-4]  # /path/to/www/assets/foo.css
        if not os.path.exists(filepath):
            cleanup.append(filepath)
        dispatch_result = DispatchResult(DispatchStatus.okay, spt, None, None, None)
        state = dict(dispatch_result=dispatch_result, response=Response())
        state['state'] = state
        resource = website.request_processor.resources.get(spt)
        content = resource.render(state, dispatch_result, None).body
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
        except Exception:
            pass


def clean_assets(www_root):
    rm_f(*[spt[:-4] for spt in find_files(www_root+'/assets/', '*.spt')])


def asset_etag(path):
    if path.endswith('.spt'):
        return ''
    if path in ETAGS:
        return ETAGS[path]
    with open(path, 'rb') as f:
        h = b64encode_s(md5(f.read()).digest())
    ETAGS[path] = h
    return h


# algorithm functions

def get_etag_for_file(dispatch_result, website, state):
    if dispatch_result.status != DispatchStatus.okay:
        return {'etag': None}
    try:
        return {'etag': asset_etag(dispatch_result.match)}
    except Exception as e:
        website.tell_sentry(e, state)
        return {'etag': None}


def try_to_serve_304(dispatch_result, request, response, etag):
    """Try to serve a 304 for static resources.
    """
    if not etag:
        # This is a request for a dynamic resource.
        return

    # Compare the etag in the request's querystring to the one we have.
    qs_etag = request.qs.get('etag')
    if qs_etag and qs_etag != etag:
        # Don't serve one version of a file as if it were another.
        raise response.error(410)

    # Compare the etag in the request's headers to the one we have.
    headers_etag = request.headers.get(b'If-None-Match', b'').decode('ascii', 'replace')
    if headers_etag and headers_etag == etag:
        # Success! We can serve a 304.
        raise response.success(304)


def add_caching_to_response(state, website, response, request=None, etag=None):
    """Set caching headers.
    """
    if response.code not in (200, 304):
        return
    if b'Cache-Control' in response.headers:
        # The caching policy has already been defined somewhere else
        return
    if etag:
        try:
            assert not response.headers.cookie
        except Exception as e:
            website.tell_sentry(e, state)
            response.headers.cookie.clear()
        # https://developers.google.com/speed/docs/best-practices/caching
        response.headers[b'Etag'] = etag.encode('ascii')
        if request.qs.get('etag'):
            # We can cache "indefinitely" when the querystring contains the etag.
            response.headers[b'Cache-Control'] = b'public, max-age=31536000, immutable'
        else:
            # Otherwise we cache for 1 hour
            response.headers[b'Cache-Control'] = b'public, max-age=3600'
    else:
        # This is a dynamic resource, disable caching by default
        response.headers[b'Cache-Control'] = b'no-cache'
