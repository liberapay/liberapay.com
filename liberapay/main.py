from __future__ import division

import base64

from six.moves import builtins
from six.moves.urllib.parse import quote as urlquote

from liberapay import canonize, fill_accept_header, insert_constants, utils, wireup
from liberapay.cron import Cron
from liberapay.models.community import Community
from liberapay.models.participant import Participant
from liberapay.security import authentication, csrf, x_frame_options
from liberapay.utils import erase_cookie, http_caching, i18n, set_cookie, timer
from liberapay.renderers import csv_dump, jinja2_htmlescaped, jinja2_html_jswrapped, jinja2_xml_min

import aspen
from aspen.website import Website


website = Website()


# Configure renderers
# ===================

website.renderer_default = 'unspecified'  # require explicit renderer, to avoid escaping bugs

website.renderer_factories['csv_dump'] = csv_dump.Factory(website)
website.renderer_factories['jinja2_htmlescaped'] = jinja2_htmlescaped.Factory(website)
website.renderer_factories['jinja2_html_jswrapped'] = jinja2_html_jswrapped.Factory(website)
website.renderer_factories['jinja2_xml_min'] = jinja2_xml_min.Factory(website)
website.default_renderers_by_media_type['text/html'] = 'jinja2_htmlescaped'
website.default_renderers_by_media_type['text/plain'] = 'jinja2'  # unescaped is fine here

def _assert(x):
    assert x, repr(x)
    return x

website.renderer_factories['jinja2'].Renderer.global_context.update(builtins.__dict__)
website.renderer_factories['jinja2'].Renderer.global_context.update({
    # This is shared via class inheritance with jinja2_htmlescaped.
    'assert': _assert,
    'Community': Community,
    'b64decode': base64.b64decode,
    'b64encode': base64.b64encode,
    'filter_profile_subnav': utils.filter_profile_subnav,
    'to_javascript': utils.to_javascript,
    'urlquote': urlquote,
})


# Wireup Algorithm
# ================

env = website.env = wireup.env()
tell_sentry = website.tell_sentry = wireup.make_sentry_teller(env)
wireup.canonical(env)
website.db = wireup.db(env)
website.mailer = wireup.mail(env, website.project_root)
wireup.billing(env)
wireup.username_restrictions(website)
wireup.load_i18n(website)
wireup.other_stuff(website, env)
wireup.accounts_elsewhere(website, env)


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
    insert_constants,
    authentication.start_user_as_anon,
    csrf.extract_token_from_cookie,
    csrf.reject_forgeries,
    authentication.authenticate_user_if_possible,

    algorithm['dispatch_request_to_filesystem'],

    http_caching.get_etag_for_file if env.cache_static else noop,
    http_caching.try_to_serve_304 if env.cache_static else noop,

    algorithm['apply_typecasters_to_path'],
    algorithm['get_resource_for_request'],
    algorithm['extract_accept_from_request'],
    fill_accept_header,
    algorithm['get_response_for_resource'],

    tell_sentry,
    algorithm['get_response_for_exception'],

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
