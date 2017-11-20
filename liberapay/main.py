from __future__ import division

from ipaddress import ip_address
import os
import signal
import string
from threading import Timer

from six import text_type
from six.moves import builtins
from six.moves.urllib.parse import quote as urlquote

import aspen
import aspen.http.mapping
from mangopay.utils import Money
import pando
from pando import json
from pando.algorithms.website import fill_response_with_output
from pando.utils import maybe_encode

from liberapay import utils, wireup
from liberapay.billing.payday import Payday, create_payday_issue
from liberapay.billing.transactions import check_all_balances
from liberapay.cron import Cron, Daily, Weekly
from liberapay.models.community import Community
from liberapay.models.participant import Participant
from liberapay.models.repository import refetch_repos
from liberapay.security import authentication, csrf, set_default_security_headers
from liberapay.utils import b64decode_s, b64encode_s, erase_cookie, http_caching, i18n, set_cookie
from liberapay.utils.currencies import MoneyBasket, fetch_currency_exchange_rates
from liberapay.utils.state_chain import (
    attach_environ_to_request, create_response_object, canonize, insert_constants,
    _dispatch_path_to_filesystem, merge_exception_into_response, return_500_for_exception,
    turn_socket_error_into_50X, overwrite_status_code_of_gateway_errors,
)
from liberapay.renderers import csv_dump, jinja2, jinja2_jswrapped, jinja2_xml_min, scss
from liberapay.website import website


application = website  # for stupid WSGI implementations


# Configure renderers
# ===================

json.register_encoder(Money, lambda m: {'amount': str(m.amount), 'currency': m.currency})
json.register_encoder(MoneyBasket, lambda b: list(b))

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
website.renderer_factories['jinja2'].Renderer.global_context['str'] = text_type
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

if not website.db:
    # Re-exec in 30 second to see if the DB is back up
    # SIGTERM is used to tell gunicorn to gracefully stop the worker
    # http://docs.gunicorn.org/en/stable/signals.html
    Timer(30.0, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()

if env.cache_static:
    http_caching.compile_assets(website)
elif env.clean_assets:
    http_caching.clean_assets(website.www_root)


# Periodic jobs
# =============

conf = website.app_conf
if conf:
    cron = Cron(website)
    cron(conf.check_db_every, website.db.self_check, True)
    cron(conf.dequeue_emails_every, Participant.dequeue_emails, True)
    cron(conf.send_newsletters_every, Participant.send_newsletters, True)
    cron(conf.refetch_repos_every, refetch_repos, True)
    cron(Weekly(weekday=3, hour=1), check_all_balances, True)
    cron(Weekly(weekday=3, hour=2), create_payday_issue, True)
    cron(conf.clean_up_counters_every, website.db.clean_up_counters, True)
    cron(Daily(hour=16), lambda: fetch_currency_exchange_rates(website.db), True)
    cron(Daily(hour=17), Payday.update_cached_amounts, True)


# Website Algorithm
# =================

noop = lambda: None
algorithm = website.algorithm
algorithm.functions = [
    algorithm['parse_environ_into_request'],
    attach_environ_to_request,
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
    i18n.add_currency_to_state,

    _dispatch_path_to_filesystem,
    algorithm['handle_dispatch_exception'],

    http_caching.get_etag_for_file if env.cache_static else noop,
    http_caching.try_to_serve_304 if env.cache_static else noop,

    algorithm['apply_typecasters_to_path'],
    algorithm['load_resource_from_filesystem'],
    algorithm['render_resource'],
    algorithm['fill_response_with_output'],

    tell_sentry,
    merge_exception_into_response,
    turn_socket_error_into_50X,
    algorithm['get_response_for_exception'],

    authentication.add_auth_to_response,
    csrf.add_token_to_response,
    http_caching.add_caching_to_response,
    set_default_security_headers,

    algorithm['delegate_error_to_simplate'],
    tell_sentry,
    return_500_for_exception,

    overwrite_status_code_of_gateway_errors,

    tell_sentry,
]


# Monkey patch aspen and pando
# ============================

if hasattr(aspen.http.mapping.Mapping, 'get_int'):
    raise Warning('aspen.http.mapping.Mapping.get_int() already exists')
aspen.http.mapping.Mapping.get_int = utils.get_int

if hasattr(pando.http.request.Request, 'source'):
    raise Warning('pando.http.request.Request.source already exists')
def _source(self):
    def f():
        addr = ip_address(self.environ[b'REMOTE_ADDR'].decode('ascii'))
        trusted_proxies = getattr(self.website, 'trusted_proxies', None)
        forwarded_for = self.headers.get(b'X-Forwarded-For')
        if not trusted_proxies or not forwarded_for:
            return addr
        for networks in trusted_proxies:
            is_trusted = False
            for network in networks:
                is_trusted = addr.is_private if network == 'private' else addr in network
                if is_trusted:
                    break
            if not is_trusted:
                return addr
            i = forwarded_for.rfind(b',')
            try:
                addr = ip_address(forwarded_for[i+1:].decode('ascii').strip())
            except (UnicodeDecodeError, ValueError):
                return addr
            if i == -1:
                return addr
            forwarded_for = forwarded_for[:i]
        return addr
    r = f()
    self.__dict__['source'] = r
    return r
pando.http.request.Request.source = property(_source)

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

if hasattr(pando.Response, 'json'):
    raise Warning('pando.Response.json() already exists')
def _json(self, obj, code=200):
    self.code = code
    self.body = json.dumps(obj)
    self.headers[b'Content-Type'] = b'application/json'
    raise self
pando.Response.json = _json

if hasattr(pando.Response, 'sanitize_untrusted_url'):
    raise Warning('pando.Response.sanitize_untrusted_url() already exists')
def _sanitize_untrusted_url(response, url):
    if isinstance(url, bytes):
        url = url.decode('utf8', 'replace')
    if not url.startswith('/') or url.startswith('//'):
        url = '/?bad_redirect=' + urlquote(url)
    host = response.request.headers[b'Host'].decode('ascii')
    # ^ this is safe because we don't accept requests with unknown hosts
    return response.website.canonical_scheme + '://' + host + url
pando.Response.sanitize_untrusted_url = _sanitize_untrusted_url

if hasattr(pando.Response, 'redirect'):
    raise Warning('pando.Response.redirect() already exists')
def _redirect(response, url, code=302, trusted_url=True):
    if not trusted_url:
        url = response.sanitize_untrusted_url(url)
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
