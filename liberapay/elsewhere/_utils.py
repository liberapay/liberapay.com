from __future__ import absolute_import, division, print_function, unicode_literals

from urllib.parse import urlsplit


def extract_domain_from_url(url):
    return urlsplit(url).hostname
