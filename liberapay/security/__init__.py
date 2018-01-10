from __future__ import absolute_import, division, print_function, unicode_literals


def set_default_security_headers(website, response, request=None):
    # Allow CORS for assets
    # The subdomains need this to access the assets on the main domain.
    if request is not None and request.path.raw.startswith('/assets/'):
        if b'Access-Control-Allow-Origin' not in response.headers:
            response.headers[b'Access-Control-Allow-Origin'] = b'*'

    # X-Frame-Options is a security measure to prevent clickjacking
    # See http://en.wikipedia.org/wiki/Clickjacking
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

    # CSP is a client-side protection against code injection (XSS)
    # https://scotthelme.co.uk/content-security-policy-an-introduction/
    if b'content-security-policy' not in response.headers:
        csp = (
            b"default-src 'self' %(main_domain)s;"
            b"script-src 'self' %(main_domain)s 'unsafe-inline';"
            b"style-src 'self' %(main_domain)s 'unsafe-inline';"
            b"connect-src *;"  # for credit card data
            b"img-src *;"
            b"reflected-xss block;"
        ) % {b'main_domain': website.canonical_host.encode('ascii')}
        csp += website.env.csp_extra.encode()
        if website.canonical_scheme == 'https':
            csp += b"upgrade-insecure-requests;"
        response.headers[b'content-security-policy'] = csp

    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection
    if b'X-XSS-Protection' not in response.headers:
        response.headers[b'X-XSS-Protection'] = b'1; mode=block'

    # https://www.w3.org/TR/referrer-policy/#referrer-policy-strict-origin-when-cross-origin
    # https://caniuse.com/referrer-policy
    if b'Referrer-Policy' not in response.headers:
        response.headers[b'Referrer-Policy'] = b'strict-origin-when-cross-origin'
