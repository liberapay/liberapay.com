from __future__ import division

import string

from six.moves import builtins
from six.moves.urllib.parse import quote as urlquote

import aspen
import aspen.http.mapping
import pando
from pando.algorithms.website import fill_response_with_output
from pando.utils import maybe_encode

from liberapay import utils, wireup
from liberapay.cron import Cron
from liberapay.models.community import Community
from liberapay.models.participant import Participant
from liberapay.security import authentication, csrf, set_default_security_headers
from liberapay.utils import b64decode_s, b64encode_s, erase_cookie, http_caching, i18n, set_cookie
from liberapay.utils.state_chain import (
    create_response_object, canonize, insert_constants,
    merge_exception_into_response, return_500_for_exception,
)
from liberapay.renderers import csv_dump, jinja2, jinja2_jswrapped, jinja2_xml_min, scss
from liberapay.website import website


# Configure renderers
# ===================

website.renderer_default = 'unspecified'  # require explicit renderer, to avoid escaping bugs

website.renderer_factories['csv_dump'] = csv_dump.Factory(website)
website.renderer_factories['jinja2'] = jinja2.Factory(website)
website.renderer_factories['jinja2_html_jswrapped'] = jinja2_jswrapped.Factory(website)
website.renderer_factories['jinja2_xml_min'] = jinja2_xml_min.Factory(website)
website.renderer_factories['scss'] = scss.Factory(website)
website.default_renderers_by_media_type['text/html'] = 'jinja2'
website.default_renderers_by_media_type['text/plain'] = 'jinja2'

def _assert(x):
    assert x, repr(x)
    return x

website.renderer_factories['jinja2'].Renderer.global_context.update(builtins.__dict__)
website.renderer_factories['jinja2'].Renderer.global_context.update({
    # This is shared via class inheritance with jinja2_* renderers.
    'assert': _assert,
    'Community': Community,
    'b64decode_s': b64decode_s,
    'b64encode_s': b64encode_s,
    'to_javascript': utils.to_javascript,
    'urlquote': urlquote,
})


# Wireup Algorithm
# ================

website.__dict__.update(wireup.full_algorithm.run(**website.__dict__))
website.__dict__.pop('state')
env = website.env
tell_sentry = website.tell_sentry

if env.cache_static:
    http_caching.compile_assets(website)
elif env.clean_assets:
    http_caching.clean_assets(website.www_root)


# Periodic jobs
# =============

conf = website.app_conf
if env.run_cron_jobs and conf:
    cron = Cron(website)
    cron(conf.update_global_stats_every, lambda: utils.update_global_stats(website))
    cron(conf.check_db_every, website.db.self_check, True)
    cron(conf.dequeue_emails_every, Participant.dequeue_emails, True)


# Website Algorithm
# =================

noop = lambda: None
algorithm = website.algorithm
algorithm.functions = [
    algorithm['parse_environ_into_request'],
    algorithm['insert_variables_for_aspen'],
    algorithm['parse_body_into_request'],
    algorithm['raise_200_for_OPTIONS'],
    create_response_object,

    canonize,
    i18n.set_up_i18n,
    insert_constants,
    authentication.start_user_as_anon,
    csrf.extract_token_from_cookie,
    csrf.reject_forgeries,
    authentication.authenticate_user_if_possible,

    algorithm['dispatch_path_to_filesystem'],
    algorithm['handle_dispatch_exception'],

    http_caching.get_etag_for_file if env.cache_static else noop,
    http_caching.try_to_serve_304 if env.cache_static else noop,

    algorithm['apply_typecasters_to_path'],
    algorithm['load_resource_from_filesystem'],
    algorithm['render_resource'],
    algorithm['fill_response_with_output'],

    tell_sentry,
    merge_exception_into_response,
    algorithm['get_response_for_exception'],

    authentication.add_auth_to_response,
    csrf.add_token_to_response,
    http_caching.add_caching_to_response,
    set_default_security_headers,

    algorithm['delegate_error_to_simplate'],
    tell_sentry,
    return_500_for_exception,

    tell_sentry,
]


# Monkey patch aspen and pando
# ============================

if hasattr(pando.Response, 'encode_url'):
    raise Warning('pando.Response.encode_url() already exists')
def _encode_url(url):
    return maybe_encode(urlquote(maybe_encode(url, 'utf8'), string.punctuation))
pando.Response.encode_url = staticmethod(_encode_url)

if hasattr(pando.Response, 'error'):
    raise Warning('pando.Response.error() already exists')
def _error(self, code, msg=''):
    self.code = code
    self.body = msg
    raise self
pando.Response.error = _error

if hasattr(pando.Response, 'success'):
    raise Warning('pando.Response.success() already exists')
def _success(self, code=200, msg=''):
    self.code = code
    self.body = msg
    raise self
pando.Response.success = _success

if hasattr(pando.Response, 'redirect'):
    raise Warning('pando.Response.redirect() already exists')
def _redirect(response, url, code=302, trusted_url=True):
    if not trusted_url:
        if isinstance(url, bytes):
            url = url.decode('utf8')
        if not url.startswith('/') or url.startswith('//'):
            url = '/?bad_redirect=' + urlquote(url)
        host = response.request.headers[b'Host'].decode('ascii')
        # ^ this is safe because we don't accept requests with unknown hosts
        url = response.website.canonical_scheme + '://' + host + url
    response.code = code
    response.headers[b'Location'] = response.encode_url(url)
    raise response
pando.Response.redirect = _redirect

if hasattr(pando.Response, 'render'):
    raise Warning('pando.Response.render() already exists')
def _render(response, path, state, **extra):
    state.update(extra)
    request_processor = state['request_processor']
    output = aspen.resources.get(request_processor, path).render(state)
    fill_response_with_output(output, response, request_processor)
    raise response
pando.Response.render = _render

if hasattr(pando.Response, 'set_cookie'):
    raise Warning('pando.Response.set_cookie() already exists')
def _set_cookie(response, *args, **kw):
    set_cookie(response.headers.cookie, *args, **kw)
pando.Response.set_cookie = _set_cookie

if hasattr(pando.Response, 'erase_cookie'):
    raise Warning('pando.Response.erase_cookie() already exists')
def _erase_cookie(response, *args, **kw):
    erase_cookie(response.headers.cookie, *args, **kw)
pando.Response.erase_cookie = _erase_cookie

if hasattr(pando.Response, 'text'):
    raise Warning('pando.Response.text already exists')
def _decode_body(self):
    body = self.body
    return body.decode('utf8') if isinstance(body, bytes) else body
pando.Response.text = property(_decode_body)
