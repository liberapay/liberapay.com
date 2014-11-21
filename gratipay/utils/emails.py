from __future__ import unicode_literals

from aspen.resources.pagination import parse_specline, split_and_escape
from aspen_jinja2_renderer import SimplateLoader
from jinja2 import Environment


jinja_env = Environment()


def compile_email_spt(fpath):
    r = {}
    with open(fpath) as f:
        pages = list(split_and_escape(f.read()))
    for i, page in enumerate(pages, 1):
        tmpl = b'\n' * page.offset + page.content
        content_type, renderer = parse_specline(page.header)
        key = 'subject' if i == 1 else content_type
        r[key] = SimplateLoader(fpath, tmpl).load(jinja_env, fpath)
    return r
