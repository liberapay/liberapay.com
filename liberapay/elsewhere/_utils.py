from __future__ import absolute_import, division, print_function, unicode_literals

try:
    from urllib.parse import quote as urlquote, quote_plus as urlquote_plus, urlsplit
except ImportError:
    from urllib import quote as _urlquote, quote_plus as _urlquote_plus
    from urlparse import urlsplit

    # Monkey-patch urllib to counter the effects of unicode_literals
    import urllib
    urllib.always_safe = urllib.always_safe.encode('ascii')
    urllib._safe_quoters.clear()

    def urlquote(string, safe=b'/'):
        if not isinstance(safe, bytes):
            safe = safe.encode('ascii', 'ignore')
        if not isinstance(string, bytes):
            string = string.encode('utf8')
        return _urlquote(string, safe)

    def urlquote_plus(string, safe=b''):
        if not isinstance(safe, bytes):
            safe = safe.encode('ascii', 'ignore')
        if not isinstance(string, bytes):
            string = string.encode('utf8')
        return _urlquote_plus(string, safe)


def extract_domain_from_url(url):
    return urlsplit(url).hostname
