from __future__ import absolute_import, division, print_function, unicode_literals

try:
    from urllib.parse import urlsplit
except ImportError:
    from urlparse import urlsplit


def extract_domain_from_url(url):
    return urlsplit(url).hostname
