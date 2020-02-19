# https://github.com/liberapay/liberapay.com/issues/1451
import sys
_init_modules = globals().get('_init_modules')
if _init_modules:
    for name in list(sys.modules):
        if name not in _init_modules:
            sys.modules.pop(name, None)
else:
    _init_modules = set(sys.modules.keys())

import builtins
from ipaddress import ip_address
import os
import signal
import string
from threading import Timer
from urllib.parse import quote as urlquote, urlencode

import aspen
import aspen.http.mapping
from aspen.request_processor.dispatcher import DispatchResult, DispatchStatus
import pando
from pando import json
from pando.state_chain import render_response
from pando.utils import maybe_encode

from liberapay import utils, wireup
from liberapay.billing.payday import Payday, create_payday_issue
from liberapay.cron import Cron, Daily, Weekly
from liberapay.exceptions import PayinMethodIsUnavailable, TooManyAttempts
from liberapay.i18n.base import (
    Bold, Country, Currency, add_currency_to_state, set_up_i18n, to_age
)
from liberapay.i18n.currencies import Money, MoneyBasket, fetch_currency_exchange_rates
from liberapay.models.account_elsewhere import refetch_elsewhere_data
from liberapay.models.community import Community
from liberapay.models.participant import Participant, clean_up_closed_accounts
from liberapay.models.repository import refetch_repos
from liberapay.payin import paypal
from liberapay.payin.cron import (
    execute_scheduled_payins, reschedule_renewals, send_upcoming_debit_notifications,
)
from liberapay.security import authentication, csrf, set_default_security_headers
from liberapay.utils import (
    b64decode_s, b64encode_s, erase_cookie, http_caching, set_cookie,
)
from liberapay.utils.emails import clean_up_emails, handle_email_bounces
from liberapay.utils.state_chain import (
    attach_environ_to_request, create_response_object, reject_requests_bypassing_proxy,
    canonize, insert_constants, enforce_rate_limits, set_output_to_None,
    add_content_disposition_header, merge_responses,
    bypass_csp_for_form_redirects, delegate_error_to_simplate, return_500_for_exception,
    turn_socket_error_into_50X, overwrite_status_code_of_gateway_errors,
)
from liberapay.utils.types import Object
from liberapay.renderers import csv_dump, jinja2, jinja2_jswrapped, jinja2_xml_min, scss
from liberapay.website import Website, website


application = website  # for stupid WSGI implementations


# Configure renderers
# ===================

json.register_encoder(Money, Money.for_json)
json.register_encoder(MoneyBasket, lambda b: list(b))
json.register_encoder(Object, lambda o: o.__dict__)

website.renderer_default = 'unspecified'  # require explicit renderer, to avoid escaping bugs

rp = website.request_processor
website.renderer_factories['csv_dump'] = csv_dump.Factory(rp)
website.renderer_factories['jinja2'] = jinja2.Factory(rp)
website.renderer_factories['jinja2_html_jswrapped'] = jinja2_jswrapped.Factory(rp)
website.renderer_factories['jinja2_xml_min'] = jinja2_xml_min.Factory(rp)
website.renderer_factories['scss'] = scss.Factory(rp)
website.default_renderers_by_media_type['text/html'] = 'jinja2'
website.default_renderers_by_media_type['text/plain'] = 'jinja2'

def _assert(x):
    assert x, repr(x)
    return x

website.renderer_factories['jinja2'].Renderer.global_context.update(builtins.__dict__)
website.renderer_factories['jinja2'].Renderer.global_context.update({
    # This is shared via class inheritance with jinja2_* renderers.
    'assert': _assert,
    'Bold': Bold,
    'Community': Community,
    'Country': Country,
    'Currency': Currency,
    'b64decode_s': b64decode_s,
    'b64encode_s': b64encode_s,
    'generate_session_token': Participant.generate_session_token,
    'to_age': to_age,
    'to_javascript': utils.to_javascript,
    'urlquote': urlquote,
})


# Configure body_parsers
# ======================

del website.body_parsers[rp.media_type_json]


# Wireup Algorithm
# ================

attributes_before = set(website.__dict__.keys())
d = wireup.full_chain.run(**dict(website.__dict__, **rp.__dict__))
d.pop('chain', None)
d.pop('exception', None)
d.pop('state', None)
for k, v in d.items():
    if k not in attributes_before:
        website.__dict__[k] = v
env = website.env
tell_sentry = website.tell_sentry

timers = []
if not website.db:
    # Re-exec in 30 second to see if the DB is back up
    if 'gunicorn' in sys.modules:
        # SIGTERM is used to tell gunicorn to gracefully stop the worker
        # http://docs.gunicorn.org/en/stable/signals.html
        timers.append(Timer(30.0, lambda: os.kill(os.getpid(), signal.SIGTERM)))
    else:
        # SIGUSR1 is used to tell apache to gracefully restart this worker
        # https://httpd.apache.org/docs/current/stopping.html
        timers.append(Timer(30.0, lambda: os.kill(os.getpid(), signal.SIGUSR1)))
    timers[-1].start()

if env.cache_static:
    http_caching.compile_assets(website)
    website.request_processor.dispatcher.build_dispatch_tree()
elif env.clean_assets:
    http_caching.clean_assets(website.www_root)
    website.request_processor.dispatcher.build_dispatch_tree()


# Periodic jobs
# =============

conf = website.app_conf
cron = website.cron = Cron(website)
if conf:
    intervals = conf.cron_intervals
    cron(intervals.get('check_db', 600), website.db.self_check, True)
    cron(intervals.get('dequeue_emails', 60), Participant.dequeue_emails, True)
    cron(intervals.get('send_newsletters', 60), Participant.send_newsletters, True)
    cron(intervals.get('refetch_elsewhere_data', 120), refetch_elsewhere_data, True)
    cron(intervals.get('refetch_repos', 60), refetch_repos, True)
    cron(Weekly(weekday=3, hour=2), create_payday_issue, True)
    cron(intervals.get('clean_up_counters', 3600), website.db.clean_up_counters, True)
    cron(Daily(hour=2), reschedule_renewals, True)
    cron(Daily(hour=3), send_upcoming_debit_notifications, True)
    cron(Daily(hour=4), execute_scheduled_payins, True)
    cron(Daily(hour=8), clean_up_closed_accounts, True)
    cron(Daily(hour=16), fetch_currency_exchange_rates, True)
    cron(Daily(hour=17), paypal.sync_all_pending_payments, True)
    cron(Daily(hour=18), Payday.update_cached_amounts, True)
    cron(intervals.get('notify_patrons', 1200), Participant.notify_patrons, True)
    cron(intervals.get('migrate_identities', 120), Participant.migrate_identities, True)
    if conf.ses_feedback_queue_url:
        cron(intervals.get('fetch_email_bounces', 60), handle_email_bounces, True)
    cron(Daily(hour=1), clean_up_emails, True)

    cron('once', website.cryptograph.rotate_stored_data, True)


# Website Algorithm
# =================

noop = lambda: None
algorithm = website.state_chain
algorithm.functions = [
    insert_constants,
    algorithm['parse_environ_into_request'],
    attach_environ_to_request,
    algorithm['raise_200_for_OPTIONS'],
    create_response_object,
    set_output_to_None,

    reject_requests_bypassing_proxy,

    canonize,
    algorithm['extract_accept_header'],
    set_default_security_headers,
    csrf.add_csrf_token_to_state,
    set_up_i18n,
    authentication.start_user_as_anon,
    csrf.reject_forgeries,
    authentication.authenticate_user_if_possible,
    add_currency_to_state,

    algorithm['dispatch_path_to_filesystem'],
    algorithm['raise_404_if_missing'],

    http_caching.get_etag_for_file if env.cache_static else noop,
    http_caching.try_to_serve_304 if env.cache_static else noop,

    enforce_rate_limits,

    algorithm['load_resource_from_filesystem'],
    algorithm['render_response'],
    add_content_disposition_header,
    algorithm['handle_negotiation_exception'],

    merge_responses,
    turn_socket_error_into_50X,

    tell_sentry,
    algorithm['get_response_for_exception'],
    delegate_error_to_simplate,

    bypass_csp_for_form_redirects,
    authentication.add_auth_to_response,
    csrf.add_token_to_response,
    http_caching.add_caching_to_response,
    overwrite_status_code_of_gateway_errors,

    tell_sentry,
    return_500_for_exception,
    tell_sentry,
]


# Monkey patch Website
# ====================

def check_payin_allowed(website, request, user, method=None):
    # Check permission
    if user.is_admin:
        pass
    elif website.app_conf.payin_methods.get(method) is False:
        raise PayinMethodIsUnavailable(method)
    # Limit payment attempts
    if request.method == 'POST':
        website.db.hit_rate_limit('payin.from-user', user.id, TooManyAttempts)
        website.db.hit_rate_limit('payin.from-ip-addr', request.source, TooManyAttempts)

Website.check_payin_allowed = check_payin_allowed


# Monkey patch python's stdlib
# ============================

from http.cookies import Morsel

Morsel._reserved['samesite'] = 'SameSite'


# Monkey patch aspen and pando
# ============================

if hasattr(aspen.http.mapping.Mapping, 'get_int'):
    raise Warning('aspen.http.mapping.Mapping.get_int() already exists')
aspen.http.mapping.Mapping.get_int = utils.get_int

if hasattr(aspen.http.mapping.Mapping, 'get_money_amount'):
    raise Warning('aspen.http.mapping.Mapping.get_money_amount() already exists')
aspen.http.mapping.Mapping.get_money_amount = utils.get_money_amount

if hasattr(aspen.http.mapping.Mapping, 'get_choice'):
    raise Warning('aspen.http.mapping.Mapping.get_choice() already exists')
aspen.http.mapping.Mapping.get_choice = utils.get_choice

if hasattr(aspen.http.mapping.Mapping, 'parse_boolean'):
    raise Warning('aspen.http.mapping.Mapping.parse_boolean() already exists')
aspen.http.mapping.Mapping.parse_boolean = utils.parse_boolean

if hasattr(aspen.http.mapping.Mapping, 'parse_date'):
    raise Warning('aspen.http.mapping.Mapping.parse_date() already exists')
aspen.http.mapping.Mapping.parse_date = utils.parse_date

if hasattr(aspen.http.mapping.Mapping, 'parse_list'):
    raise Warning('aspen.http.mapping.Mapping.parse_list() already exists')
aspen.http.mapping.Mapping.parse_list = utils.parse_list

if hasattr(aspen.http.request.Querystring, 'derive'):
    raise Warning('aspen.http.request.Querystring.derive() already exists')
def _Querystring_derive(self, **kw):
    new_qs = aspen.http.mapping.Mapping(self)
    for k, v in kw.items():
        if v is None:
            new_qs.popall(k, None)
        else:
            new_qs[k] = v
    return '?' + urlencode(new_qs, doseq=True)
aspen.http.request.Querystring.derive = _Querystring_derive

if hasattr(aspen.http.request.Querystring, 'serialize'):
    raise Warning('aspen.http.request.Querystring.serialize() already exists')
def _Querystring_serialize(self, **kw):
    return ('?' + urlencode(self, doseq=True)) if self else ''
aspen.http.request.Querystring.serialize = _Querystring_serialize

if hasattr(pando.http.request.Request, 'source'):
    raise Warning('pando.http.request.Request.source already exists')
def _source(self):
    def f():
        addr = self.environ.get('REMOTE_ADDR') or self.environ[b'REMOTE_ADDR']
        addr = ip_address(addr.decode('ascii') if type(addr) is bytes else addr)
        trusted_proxies = getattr(self.website, 'trusted_proxies', None)
        forwarded_for = self.headers.get(b'X-Forwarded-For')
        self.__dict__['bypasses_proxy'] = bool(trusted_proxies)
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
                if networks is trusted_proxies[-1]:
                    break
                return addr
            forwarded_for = forwarded_for[:i]
        self.__dict__['bypasses_proxy'] = False
        return addr
    r = f()
    self.__dict__['source'] = r
    return r
pando.http.request.Request.source = property(_source)

if hasattr(pando.http.request.Request, 'bypasses_proxy'):
    raise Warning('pando.http.request.Request.bypasses_proxy already exists')
def _bypasses_proxy(self):
    self.source
    return self.__dict__['bypasses_proxy']
pando.http.request.Request.bypasses_proxy = property(_bypasses_proxy)

if hasattr(pando.http.request.Request, 'find_input_name'):
    raise Warning('pando.http.request.Request.find_input_name already exists')
def _find_input_name(self, value):
    assert isinstance(self.body, aspen.http.mapping.Mapping)
    r = None
    for k, values in self.body.items():
        if any(map(value.__eq__, values)):
            r = k
    return r
pando.http.request.Request.find_input_name = _find_input_name

if hasattr(pando.Response, 'encode_url'):
    raise Warning('pando.Response.encode_url() already exists')
def _encode_url(url):
    return maybe_encode(urlquote(url, string.punctuation))
pando.Response.encode_url = staticmethod(_encode_url)

if hasattr(pando.Response, 'error'):
    raise Warning('pando.Response.error() already exists')
def _error(self, code, msg=''):
    self.code = code
    self.body = msg
    return self
pando.Response.error = _error

if hasattr(pando.Response, 'invalid_input'):
    raise Warning('pando.Response.invalid_input() already exists')
def _invalid_input(self, input_value, input_name, input_location, code=400,
                   msg="`%s` value %s in request %s is invalid or unsupported"):
    self.code = code
    input_value = repr(input_value)
    if len(input_value) > 50:
        input_value = input_value[:24] + u'[…]' + input_value[-24:]
    self.body = msg % (input_name, input_value, input_location)
    raise self
pando.Response.invalid_input = _invalid_input

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

if hasattr(pando.Response, 'refresh'):
    raise Warning('pando.Response.refresh() already exists')
def _refresh(response, state, **extra):
    # https://en.wikipedia.org/wiki/Meta_refresh
    raise response.render('simplates/refresh.spt', state, **extra)
pando.Response.refresh = _refresh

if hasattr(pando.Response, 'render'):
    raise Warning('pando.Response.render() already exists')
def _render(response, path, state, **extra):
    state.update(extra)
    if 'dispatch_result' not in state:
        state['dispatch_result'] = DispatchResult(
            DispatchStatus.okay, path, None, None, None
        )
    website = state['website']
    resource = website.request_processor.resources.get(path)
    render_response(state, resource, response, website)
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
