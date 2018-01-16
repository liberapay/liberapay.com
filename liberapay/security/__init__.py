from __future__ import absolute_import, division, print_function, unicode_literals


def set_default_security_headers(website, response, request=None):
    # Allow CORS for assets
    # The subdomains need this to access the assets on the main domain.
    if request is not None and request.path.raw.startswith('/assets/'):
        response.headers[b'Access-Control-Allow-Origin'] = b'*'

    # X-Frame-Options is a security measure to prevent clickjacking
    # See http://en.wikipedia.org/wiki/Clickjacking
    response.headers[b'X-Frame-Options'] = b'SAMEORIGIN'

    # CSP is a client-side protection against code injection (XSS)
    # https://scotthelme.co.uk/content-security-policy-an-introduction/
    csp = (
        b"default-src 'self' %(main_domain)s;"
        b"connect-src 'self' *.liberapay.org *.mangopay.com *.payline.com;"
        b"form-action 'self';"
        b"img-src * blob: data:;"
        b"object-src 'none';"
    ) % {b'main_domain': website.canonical_host.encode('ascii')}
    csp += website.env.csp_extra.encode()
    if website.canonical_scheme == 'https':
        csp += b"upgrade-insecure-requests;"
    response.headers[b'content-security-policy'] = csp

    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection
    response.headers[b'X-XSS-Protection'] = b'1; mode=block'

    # https://www.w3.org/TR/referrer-policy/#referrer-policy-strict-origin-when-cross-origin
    # https://caniuse.com/referrer-policy
    response.headers[b'Referrer-Policy'] = b'strict-origin-when-cross-origin'
