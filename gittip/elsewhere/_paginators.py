"""Helper functions to handle pagination of API responses
"""
from __future__ import unicode_literals


def _relativize_urls(base, urls):
    i = len(base)
    r = {}
    for link_key, url in urls.items():
        if not url.startswith(base):
            raise ValueError('"%s" is not a prefix of "%s"' % (base, url))
        r[link_key] = url[i:]
    return r


links_keys = set('prev next first last'.split())


def header_links_paginator():
    def f(self, response, parsed):
        links = {k: v['url'] for k, v in response.links.items() if k in links_keys}
        total_count = -1 if links else len(parsed)
        return parsed, total_count, _relativize_urls(self.api_url, links)
    return f


def keys_paginator(**kw):
    page_key = kw.get('page', 'values')
    total_count_key = kw.get('total_count', 'size')
    links_keys_map = tuple((k, kw.get(k, k)) for k in links_keys)
    def f(self, response, parsed):
        page = parsed[page_key]
        links = {k: parsed[k2] for k, k2 in links_keys_map if parsed.get(k2)}
        total_count = parsed.get(total_count_key, -1) if links else len(page)
        return page, total_count, _relativize_urls(self.api_url, links)
    return f
