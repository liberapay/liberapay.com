from __future__ import unicode_literals

from aspen.simplates.pagination import parse_specline, split_and_escape
from aspen_jinja2_renderer import SimplateLoader
from jinja2 import Environment

from liberapay.constants import JINJA_ENV_COMMON


( VERIFICATION_MISSING
, VERIFICATION_FAILED
, VERIFICATION_EXPIRED
, VERIFICATION_REDUNDANT
, VERIFICATION_STYMIED
, VERIFICATION_SUCCEEDED
 ) = range(6)


jinja_env = Environment(**JINJA_ENV_COMMON)
jinja_env_html = Environment(
    autoescape=True, extensions=['jinja2.ext.autoescape'],
    **JINJA_ENV_COMMON
)

def compile_email_spt(fpath):
    r = {}
    with open(fpath) as f:
        pages = list(split_and_escape(f.read()))
    for i, page in enumerate(pages, 1):
        tmpl = b'\n' * page.offset + page.content
        content_type, renderer = parse_specline(page.header)
        key = 'subject' if i == 1 else content_type
        env = jinja_env_html if content_type == 'text/html' else jinja_env
        r[key] = SimplateLoader(fpath, tmpl).load(env, fpath)
    return r
