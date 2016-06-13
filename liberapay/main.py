from __future__ import division

from six.moves import builtins
from six.moves.urllib.parse import quote as urlquote

import aspen
import aspen.http.mapping

from liberapay import canonize, fill_accept_header, insert_constants, utils, wireup
from liberapay.cron import Cron
from liberapay.models.community import Community
from liberapay.models.participant import Participant
from liberapay.security import authentication, csrf, allow_cors_for_assets, x_frame_options
from liberapay.utils import b64decode_s, b64encode_s, erase_cookie, http_caching, i18n, set_cookie
from liberapay.renderers import csv_dump, jinja2_htmlescaped, jinja2_html_jswrapped, jinja2_xml_min
from liberapay.website import website


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

if env.run_cron_jobs:
    conf = website.app_conf
    cron = Cron(website)
    cron(conf.update_global_stats_every, lambda: utils.update_global_stats(website))
    cron(conf.check_db_every, website.db.self_check, True)
    cron(conf.dequeue_emails_every, Participant.dequeue_emails, True)


# Website Algorithm
# =================

def return_500_for_exception(website, exception):
    response = aspen.Response(500)
    if website.show_tracebacks:
        import traceback
        response.body = traceback.format_exc()
    else:
        response.body = (
            "Uh-oh, you've found a serious bug. Sorry for the inconvenience, "
            "we'll get it fixed ASAP."
        )
    return {'response': response, 'exception': None}


noop = lambda: None
algorithm = website.algorithm
algorithm.functions = [
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
    allow_cors_for_assets,

    algorithm['delegate_error_to_simplate'],
    tell_sentry,
    return_500_for_exception,

    tell_sentry,
]


# Monkey patch aspen
# ==================

pop = aspen.http.mapping.Mapping.pop
def _pop(self, name, default=aspen.http.mapping.NO_DEFAULT):
    try:
        return pop(self, name, default)
    except KeyError:
        raise aspen.Response(400, "Missing key: %s" % repr(name))
aspen.http.mapping.Mapping.pop = _pop

if hasattr(aspen.Response, 'redirect'):
    raise Warning('aspen.Response.redirect() already exists')
def _redirect(response, url, code=302):
    response.code = code
    response.headers['Location'] = url
    raise response
aspen.Response.redirect = _redirect

if hasattr(aspen.Response, 'render'):
    raise Warning('aspen.Response.render() already exists')
def _render(response, path, state, **extra):
    state.update(extra)
    assert response is state['response']
    aspen.resources.get(state['website'], path).respond(state)
    raise response
aspen.Response.render = _render

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
