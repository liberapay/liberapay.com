from __future__ import absolute_import, division, print_function, unicode_literals


def allow_cors_for_assets(response, request=None):
    """The subdomains need this to access the assets on the main domain.
    """
    if request is not None and request.path.raw.startswith('/assets/'):
        if b'Access-Control-Allow-Origin' not in response.headers:
            response.headers[b'Access-Control-Allow-Origin'] = b'*'


def x_frame_options(response):
    """X-Frame-Origin

    This is a security measure to prevent clickjacking:
    http://en.wikipedia.org/wiki/Clickjacking

    """
    if b'X-Frame-Options' not in response.headers:
        response.headers[b'X-Frame-Options'] = b'SAMEORIGIN'
    elif response.headers[b'X-Frame-Options'] == b'ALLOWALL':

        # ALLOWALL is non-standard. It's useful as a signal from a simplate
        # that it doesn't want X-Frame-Options set at all, but because it's
        # non-standard we don't send it. Instead we unset the header entirely,
        # which has the desired effect of allowing framing indiscriminately.
        #
        # Refs.:
        #
        #   http://en.wikipedia.org/wiki/Clickjacking#X-Frame-Options
        #   http://ipsec.pl/node/1094

        del response.headers[b'X-Frame-Options']

    if b'content-security-policy' not in response.headers:
        response.headers[b'content-security-policy'] = (
            b"default-src 'self';"
            b"script-src 'self' 'unsafe-inline';"
            b"style-src 'self' 'unsafe-inline';"
            b"img-src *;"
            b"upgrade-insecure-requests;"
            b"block-all-mixed-content;"
            b"reflected-xss block;"
        )
