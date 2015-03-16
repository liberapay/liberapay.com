from __future__ import division

import base64

import gratipay
import gratipay.wireup
from gratipay import canonize, utils
from gratipay.cron import Cron
from gratipay.models.participant import Participant
from gratipay.security import authentication, csrf, x_frame_options
from gratipay.utils import erase_cookie, http_caching, i18n, set_cookie, timer
from gratipay.version import get_version
from gratipay.renderers import jinja2_htmlescaped

import aspen
from aspen.website import Website


website = Website([])


# Configure renderers
# ===================

website.renderer_default = 'unspecified'  # require explicit renderer, to avoid escaping bugs

website.renderer_factories['jinja2_htmlescaped'] = jinja2_htmlescaped.Factory(website)
website.default_renderers_by_media_type['text/html'] = 'jinja2_htmlescaped'
website.default_renderers_by_media_type['text/plain'] = 'jinja2'  # unescaped is fine here

website.renderer_factories['jinja2'].Renderer.global_context = {
    # This is shared via class inheritance with jinja2_htmlescaped.
    'b64encode': base64.b64encode,
    'enumerate': enumerate,
    'filter_profile_subnav': utils.filter_profile_subnav,
    'float': float,
    'len': len,
    'range': range,
    'str': str,
    'to_javascript': utils.to_javascript,
    'type': type,
    'unicode': unicode,
}


# Wireup Algorithm
# ================

exc = None
try:
    website.version = get_version()
except Exception, e:
    exc = e
    website.version = 'x'


env = website.env = gratipay.wireup.env()
tell_sentry = website.tell_sentry = gratipay.wireup.make_sentry_teller(env)
gratipay.wireup.canonical(env)
website.db = gratipay.wireup.db(env)
website.mailer = gratipay.wireup.mail(env, website.project_root)
gratipay.wireup.billing(env)
gratipay.wireup.username_restrictions(website)
gratipay.wireup.load_i18n(website.project_root, tell_sentry)
gratipay.wireup.other_stuff(website, env)
gratipay.wireup.accounts_elsewhere(website, env)

if exc:
    tell_sentry(exc, {})


# Periodic jobs
# =============

cron = Cron(website)
cron(env.update_global_stats_every, lambda: utils.update_global_stats(website))
cron(env.check_db_every, website.db.self_check, True)
cron(env.dequeue_emails_every, Participant.dequeue_emails, True)


# Website Algorithm
# =================

noop = lambda: None
algorithm = website.algorithm
algorithm.functions = [
    timer.start,
    algorithm['parse_environ_into_request'],
    algorithm['parse_body_into_request'],
    algorithm['raise_200_for_OPTIONS'],

    canonize,
    i18n.set_up_i18n,
    authentication.start_user_as_anon,
    authentication.authenticate_user_if_possible,
    csrf.extract_token_from_cookie,
    csrf.reject_forgeries,

    algorithm['dispatch_request_to_filesystem'],

    http_caching.get_etag_for_file if website.cache_static else noop,
    http_caching.try_to_serve_304 if website.cache_static else noop,

    algorithm['apply_typecasters_to_path'],
    algorithm['get_resource_for_request'],
    algorithm['extract_accept_from_request'],
    algorithm['get_response_for_resource'],

    tell_sentry,
    algorithm['get_response_for_exception'],

    gratipay.set_version_header,
    authentication.add_auth_to_response,
    csrf.add_token_to_response,
    http_caching.add_caching_to_response,
    x_frame_options,

    algorithm['log_traceback_for_5xx'],
    algorithm['delegate_error_to_simplate'],
    tell_sentry,
    algorithm['log_traceback_for_exception'],
    algorithm['log_result_of_request'],

    timer.end,
    tell_sentry,
]


# Monkey patch aspen.Response
# ===========================

if hasattr(aspen.Response, 'redirect'):
    raise Warning('aspen.Response.redirect() already exists')
def _redirect(response, url):
    response.code = 302
    response.headers['Location'] = url
    raise response
aspen.Response.redirect = _redirect

if hasattr(aspen.Response, 'set_cookie'):
    raise Warning('aspen.Response.set_cookie() already exists')
def _set_cookie(response, *args, **kw):
    set_cookie(response.headers.cookie, *args, **kw)
aspen.Response.set_cookie = _set_cookie

if hasattr(aspen.Response, 'erase_cookie'):
    raise Warning('aspen.Response.erase_cookie() already exists')
def _erase_cookie(response, *args, **kw):
    erase_cookie(response.headers.cookie, *args, **kw)
aspen.Response.erase_cookie = _erase_cookie
