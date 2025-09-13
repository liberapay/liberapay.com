# https://github.com/liberapay/liberapay.com/issues/1451
from importlib import reload
import sys
_init_modules = globals().get('_init_modules')
if _init_modules:
    for name, module in list(sys.modules.items()):
        if name not in _init_modules:
            reload(module)
else:
    _init_modules = set(sys.modules.keys())

import builtins
import http.cookies
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

from liberapay import utils
from liberapay.billing.payday import Payday, create_payday_issue
from liberapay.cron import Cron, Daily, Weekly
from liberapay.exceptions import PayinMethodIsUnavailable, TooManyAttempts
from liberapay.i18n.base import (
    Bold, Country, Currency, add_currency_to_state, set_up_i18n, to_age
)
from liberapay.i18n.currencies import Money, MoneyBasket, fetch_currency_exchange_rates
from liberapay.models.account_elsewhere import refetch_elsewhere_data
from liberapay.models.community import Community
from liberapay.models.participant import (
    Participant, clean_up_closed_accounts, free_up_usernames,
    send_account_disabled_notifications, send_account_flagged_notifications,
    generate_profile_description_missing_notifications
)
from liberapay.models.repository import refetch_repos
from liberapay.payin import paypal
from liberapay.payin.cron import (
    detect_stuck_payins, execute_reviewed_payins, execute_scheduled_payins,
    reschedule_renewals, send_upcoming_debit_notifications,
)
from liberapay.security import authentication, csrf, set_default_security_headers
from liberapay.security.csp import csp_allow
from liberapay.utils import (
    b64decode_s, b64encode_s, erase_cookie, http_caching, set_cookie,
)
from liberapay.utils.emails import clean_up_emails, handle_email_bounces
from liberapay.utils.state_chain import (
    add_content_disposition_header,
    add_state_to_context,
    attach_environ_to_request,
    bypass_csp_for_form_redirects,
    canonize,
    create_response_object,
    delegate_error_to_simplate,
    detect_obsolete_browsers,
    drop_accept_all_header,
    enforce_rate_limits,
    get_response_for_exception,
    insert_constants,
    merge_responses,
    no_response_body_for_HEAD_requests,
    overwrite_status_code_of_gateway_errors,
    raise_response_to_OPTIONS_request,
    return_500_for_exception,
    set_output_to_None,
    turn_socket_error_into_50X,
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
website.default_renderers_by_media_type['-/subject'] = 'jinja2'
website.default_renderers_by_media_type['text/html'] = 'jinja2'
website.default_renderers_by_media_type['text/plain'] = 'jinja2'

def _assert(x, msg=None):
    if not x:
        raise AssertionError(msg or repr(x))
    return x

def soft_assert(x, msg):
    if not x:
        try:
            raise AssertionError(msg)
        except AssertionError as e:
            website.tell_sentry(e)
    return x

website.renderer_factories['jinja2'].Renderer.global_context.update(builtins.__dict__)
website.renderer_factories['jinja2'].Renderer.global_context.update({
    # This is shared via class inheritance with jinja2_* renderers.
    "ANON": authentication.ANON,
    'assert': _assert,
    'b64decode_s': b64decode_s,
    'b64encode_s': b64encode_s,
    'Bold': Bold,
    'Community': Community,
    'Country': Country,
    'Currency': Currency,
    'generate_session_token': Participant.generate_session_token,
    'soft_assert': soft_assert,
    'to_age': to_age,
    'to_javascript': utils.to_javascript,
    'urlquote': urlquote,
})


# Configure body_parsers
# ======================

del website.body_parsers[rp.media_type_json]

def default_body_parser(body_bytes, headers):
    if body_bytes:
        raise pando.exceptions.UnknownBodyType(headers.get(b'Content-Type'))
    else:
        return pando.http.mapping.Mapping()

website.body_parsers[''] = default_body_parser


# Wireup Algorithm
# ================

website.wireup()
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
    cron(intervals.get('send_account_disabled_notifications', 600), send_account_disabled_notifications, True)
    cron(intervals.get('send_account_flagged_notifications', 600), send_account_flagged_notifications, True)
    cron(intervals.get('refetch_elsewhere_data', 30), refetch_elsewhere_data, True)
    cron(intervals.get('refetch_repos', 20), refetch_repos, True)
    cron(Weekly(weekday=3, hour=2), create_payday_issue, True)
    cron(intervals.get('clean_up_counters', 3600), website.db.clean_up_counters, True)
    cron(Daily(hour=1), clean_up_emails, True)
    cron(Daily(hour=2), fetch_currency_exchange_rates, True)
    cron(Daily(hour=3), reschedule_renewals, True)
    cron(Daily(hour=4), send_upcoming_debit_notifications, True)
    cron(Daily(hour=5), execute_scheduled_payins, True)
    cron(Daily(hour=8), clean_up_closed_accounts, True)
    cron(Daily(hour=12), generate_profile_description_missing_notifications, True)
    cron(Daily(hour=13), paypal.sync_all_pending_payments, True)
    cron(Daily(hour=14), detect_stuck_payins, True)
    cron(Daily(hour=18), Payday.update_cached_amounts, True)
    cron(Daily(hour=19), Participant.delete_old_feedback, True)
    cron(Daily(hour=20), free_up_usernames, True)
    cron(intervals.get('notify_patrons', 1200), Participant.notify_patrons, True)
    if conf.ses_feedback_queue_url:
        cron(intervals.get('fetch_email_bounces', 60), handle_email_bounces, True)
    cron(intervals.get('execute_reviewed_payins', 3600), execute_reviewed_payins, True)

    cron('irregular', website.cryptograph.rotate_stored_data, True)


# Website Algorithm
# =================

noop = lambda: None
algorithm = website.state_chain
algorithm.functions = [
    add_state_to_context,
    insert_constants,
    algorithm['parse_environ_into_request'],
    attach_environ_to_request,
    create_response_object,
    raise_response_to_OPTIONS_request,
    set_output_to_None,

    canonize,
    algorithm['extract_accept_header'],
    drop_accept_all_header,
    set_default_security_headers,
    csrf.add_csrf_token_to_state,
    set_up_i18n,
    authentication.start_user_as_anon,

    algorithm['dispatch_path_to_filesystem'],
    http_caching.get_etag_for_file if env.cache_static else noop,
    http_caching.try_to_serve_304 if env.cache_static else noop,

    csrf.reject_forgeries,
    authentication.authenticate_user_if_possible,
    add_currency_to_state,
    detect_obsolete_browsers,
    algorithm['raise_404_if_missing'],
    enforce_rate_limits,

    algorithm['load_resource_from_filesystem'],
    algorithm['render_response'],
    add_content_disposition_header,
    algorithm['handle_negotiation_exception'],

    merge_responses,
    turn_socket_error_into_50X,
    tell_sentry,
    get_response_for_exception,
    delegate_error_to_simplate,

    bypass_csp_for_form_redirects,
    authentication.refresh_user_session,
    csrf.add_token_to_response,
    http_caching.add_caching_to_response,
    overwrite_status_code_of_gateway_errors,
    no_response_body_for_HEAD_requests,

    tell_sentry,
    return_500_for_exception,
    tell_sentry,
]


# Monkey patch Website
# ====================

def check_payin_allowed(website, request, user, method=None):
    # Check permission
    if user.is_acting_as('admin'):
        pass
    elif website.app_conf.payin_methods.get(method) is False:
        raise PayinMethodIsUnavailable(method)
    # Limit payment attempts
    if request.method == 'POST':
        website.db.hit_rate_limit('payin.from-user', user.id, TooManyAttempts)
        website.db.hit_rate_limit('payin.from-ip-addr', request.source, TooManyAttempts)

Website.check_payin_allowed = check_payin_allowed


# Monkey patch aspen and pando
# ============================

if hasattr(aspen.http.mapping.Mapping, 'get_int'):
    raise Warning('aspen.http.mapping.Mapping.get_int() already exists')
aspen.http.mapping.Mapping.get_int = utils.get_int

if hasattr(aspen.http.mapping.Mapping, 'get_currency'):
    raise Warning('aspen.http.mapping.Mapping.get_currency() already exists')
aspen.http.mapping.Mapping.get_currency = utils.get_currency

if hasattr(aspen.http.mapping.Mapping, 'get_money_amount'):
    raise Warning('aspen.http.mapping.Mapping.get_money_amount() already exists')
aspen.http.mapping.Mapping.get_money_amount = utils.get_money_amount

if hasattr(aspen.http.mapping.Mapping, 'get_choice'):
    raise Warning('aspen.http.mapping.Mapping.get_choice() already exists')
aspen.http.mapping.Mapping.get_choice = utils.get_choice

if hasattr(aspen.http.mapping.Mapping, 'get_color'):
    raise Warning('aspen.http.mapping.Mapping.get_color() already exists')
aspen.http.mapping.Mapping.get_color = utils.get_color

if hasattr(aspen.http.mapping.Mapping, 'word'):
    raise Warning('aspen.http.mapping.Mapping.word() already exists')
aspen.http.mapping.Mapping.word = utils.word

if hasattr(aspen.http.mapping.Mapping, 'parse_boolean'):
    raise Warning('aspen.http.mapping.Mapping.parse_boolean() already exists')
aspen.http.mapping.Mapping.parse_boolean = utils.parse_boolean

if hasattr(aspen.http.mapping.Mapping, 'parse_ternary'):
    raise Warning('aspen.http.mapping.Mapping.parse_ternary() already exists')
aspen.http.mapping.Mapping.parse_ternary = utils.parse_ternary

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
del _Querystring_derive

if hasattr(aspen.http.request.Querystring, 'serialize'):
    raise Warning('aspen.http.request.Querystring.serialize() already exists')
def _Querystring_serialize(self, **kw):
    return ('?' + urlencode(self, doseq=True)) if self else ''
aspen.http.request.Querystring.serialize = _Querystring_serialize
del _Querystring_serialize

pando.http.request.Headers.__init__ = pando.http.mapping.CaseInsensitiveMapping.__init__

if hasattr(pando.http.request.Request, 'cookies'):
    raise Warning('pando.http.request.Request.cookies already exists')
def _cookies(self):
    cookies = self.__dict__.get('cookies')
    if cookies is None:
        header = self.headers.get(b'Cookie', b'').decode('utf8', 'backslashreplace')
        cookies = {}
        for item in header.split(';'):
            try:
                k, v = item.split('=', 1)
            except ValueError:
                continue
            k = k.strip()
            if len(v) > 1 and v.startswith('"') and v.endswith('"'):
                v = http.cookies._unquote(v)
            cookies[k] = v
        self.__dict__['cookies'] = cookies
    return cookies
pando.http.request.Request.cookies = property(_cookies)
del _cookies

if hasattr(pando.http.request.Request, 'queued_success_messages'):
    raise Warning('pando.http.request.Request.queued_success_messages already exists')
def _queued_success_messages(self):
    if not hasattr(self, '_queued_success_messages'):
        self._queued_success_messages = map(b64decode_s, self.qs.all('success'))
    return self._queued_success_messages
pando.http.request.Request.queued_success_messages = property(_queued_success_messages)
del _queued_success_messages

if hasattr(pando.http.request.Request, 'source'):
    raise Warning('pando.http.request.Request.source already exists')
def _source(self):
    if 'source' not in self.__dict__:
        addr = (
            self.headers.get(b'Cf-Connecting-Ip') or
            self.environ.get(b'REMOTE_ADDR') or
            self.environ.get('REMOTE_ADDR') or
            '0.0.0.0'
        )
        if isinstance(addr, bytes):
            addr = addr.decode()
        self.__dict__['source'] = ip_address(addr)
    return self.__dict__['source']
pando.http.request.Request.source = property(_source)
del _source

if hasattr(pando.http.request.Request, 'find_input_name'):
    raise Warning('pando.http.request.Request.find_input_name already exists')
def _find_input_name(self, value):
    assert isinstance(self.body, aspen.http.mapping.Mapping)
    for k, values in self.body.items():
        if any(map(value.__eq__, values)):
            return k
pando.http.request.Request.find_input_name = _find_input_name
del _find_input_name

if hasattr(pando.Response, 'csp_allow'):
    raise Warning('pando.Response.csp_allow() already exists')
pando.Response.csp_allow = csp_allow

if hasattr(pando.Response, 'encode_url'):
    raise Warning('pando.Response.encode_url() already exists')
def _encode_url(url):
    return maybe_encode(urlquote(url, string.punctuation))
pando.Response.encode_url = staticmethod(_encode_url)
del _encode_url

if hasattr(pando.Response, 'error'):
    raise Warning('pando.Response.error() already exists')
def _error(self, code, msg=''):
    self.code = code
    self.body = msg
    return self
pando.Response.error = _error
del _error

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
del _invalid_input

if hasattr(pando.Response, 'success'):
    raise Warning('pando.Response.success() already exists')
def _success(self, code=200, msg=''):
    self.code = code
    self.body = msg
    raise self
pando.Response.success = _success
del _success

if hasattr(pando.Response, 'json'):
    raise Warning('pando.Response.json() already exists')
def _json(self, obj, code=200):
    self.code = code
    self.body = json.dumps(obj)
    self.headers[b'Content-Type'] = b'application/json'
    raise self
pando.Response.json = _json
del _json

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
del _sanitize_untrusted_url

if hasattr(pando.Response, 'redirect'):
    raise Warning('pando.Response.redirect() already exists')
def _redirect(response, url, code=302, trusted_url=True):
    if not trusted_url:
        url = response.sanitize_untrusted_url(url)
    response.code = code
    response.headers[b'Location'] = response.encode_url(url)
    raise response
pando.Response.redirect = _redirect
del _redirect

if hasattr(pando.Response, 'refresh'):
    raise Warning('pando.Response.refresh() already exists')
def _refresh(response, state, **extra):
    # https://en.wikipedia.org/wiki/Meta_refresh
    raise response.render('simplates/refresh.spt', state, **extra)
pando.Response.refresh = _refresh
del _refresh

if hasattr(pando.Response, 'render'):
    raise Warning('pando.Response.render() already exists')
def _render(response, path, state, **extra):
    # Facilitate passing variables to the simplate by injecting them into the
    # state dict here.
    state.update(extra)
    # Ensure that we actually render the simplate, as opposed to possibly
    # failing when trying to determine which of its pages to render.
    accept_header = state.get('accept_header')
    if accept_header and '*/*' not in accept_header:
        accept_header += ',*/*'
    # If there's an extension at the end of the URL path, and the simplate has a
    # page for the corresponding media type, pick that page.
    dispatch_result = state.get('dispatch_result')
    if dispatch_result and dispatch_result.extension:
        if accept_header:
            accept_header = dispatch_result.extension + ',' + accept_header
        else:
            accept_header = dispatch_result.extension + ',*/*'
    state['accept_header'] = accept_header
    state['dispatch_result'] = DispatchResult(
        DispatchStatus.okay, path, None, None, None
    )
    # Load the simplate, render it and raise the response.
    website = state['website']
    resource = website.request_processor.resources.get(path)
    render_response(state, resource, response, website)
    raise response
pando.Response.render = _render
del _render

if hasattr(pando.Response, 'set_cookie'):
    raise Warning('pando.Response.set_cookie() already exists')
def _set_cookie(response, *args, **kw):
    set_cookie(response.headers.cookie, *args, **kw)
pando.Response.set_cookie = _set_cookie
del _set_cookie

if hasattr(pando.Response, 'erase_cookie'):
    raise Warning('pando.Response.erase_cookie() already exists')
def _erase_cookie(response, *args, **kw):
    erase_cookie(response.headers.cookie, *args, **kw)
pando.Response.erase_cookie = _erase_cookie
del _erase_cookie

if hasattr(pando.Response, 'text'):
    raise Warning('pando.Response.text already exists')
def _decode_body(self):
    body = self.body
    return body.decode('utf8') if isinstance(body, bytes) else body
pando.Response.text = property(_decode_body)
del _decode_body

def _str(self):
    r = f"{self.code} {self._status()}"
    if self.code >= 301 and self.code < 400 and b'Location' in self.headers:
        r += f" (Location: {self.headers[b'Location'].decode('ascii', 'backslashreplace')})"
    body = self.body
    if body:
        if isinstance(body, bytes):
            body = body.decode('ascii', 'backslashreplace')
        r += f":\n{body}"
    return r
pando.Response.__str__ = _str
del _str

# Log some performance information
# ================================

def get_process_stats():
    from resource import getrusage, RUSAGE_SELF
    ru = getrusage(RUSAGE_SELF)
    total_time = ru.ru_utime + ru.ru_stime
    u2s_ratio = ru.ru_utime / total_time
    # Simple Linux-only way to get the current process' memory footprint.
    # Doc: https://www.kernel.org/doc/html/latest/filesystems/proc.html
    try:
        with open('/proc/self/status', 'r') as f:
            d = dict(map(str.strip, line.split(':', 1)) for line in f)
            res_mem, res_mem_peak = d['VmRSS'], d['VmHWM']
            del d
    except FileNotFoundError:
        res_mem = res_mem_peak = '<unknown>'
    return (
        f"Process {os.getpid()} is ready. "
        f"Elapsed time: {total_time:.3f}s ({u2s_ratio:.1%} in userland). "
        f"Resident memory: {res_mem} now, {res_mem_peak} at peak. "
    )

website.logger.info(get_process_stats())
