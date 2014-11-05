from __future__ import division

from decimal import Decimal as D
import base64
import threading
import time
import traceback

import gratipay
import gratipay.wireup
from gratipay import canonize, utils
from gratipay.security import authentication, csrf, x_frame_options
from gratipay.utils import cache_static, i18n, set_cookie, timer
from gratipay.version import get_version


import aspen
from aspen import log_dammit


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


# Wireup Algorithm
# ================

exc = None
try:
    website.version = get_version()
except Exception, e:
    exc = e
    website.version = 'x'


website.renderer_default = "jinja2"

website.renderer_factories['jinja2'].Renderer.global_context = {
    'b64encode': base64.b64encode,
    'enumerate': enumerate,
    'float': float,
    'len': len,
    'range': range,
    'str': str,
    'type': type,
    'unicode': unicode,
}


env = website.env = gratipay.wireup.env()
tell_sentry = website.tell_sentry = gratipay.wireup.make_sentry_teller(env)
gratipay.wireup.canonical(env)
website.db = gratipay.wireup.db(env)
website.mailer = gratipay.wireup.mail(env, website.project_root)
gratipay.wireup.billing(env)
gratipay.wireup.username_restrictions(website)
gratipay.wireup.nanswers(env)
gratipay.wireup.load_i18n(website.project_root, tell_sentry)
gratipay.wireup.other_stuff(website, env)
gratipay.wireup.accounts_elsewhere(website, env)

if exc:
    tell_sentry(exc)


# Periodic jobs
# =============

conn = website.db.get_connection().__enter__()

def cron(period, func, exclusive=False):
    def f():
        if period <= 0:
            return
        sleep = time.sleep
        if exclusive:
            cursor = conn.cursor()
            try_lock = lambda: cursor.one("SELECT pg_try_advisory_lock(0)")
        has_lock = False
        while 1:
            try:
                if exclusive and not has_lock:
                    has_lock = try_lock()
                if not exclusive or has_lock:
                    func()
            except Exception, e:
                tell_sentry(e)
                log_dammit(traceback.format_exc().strip())
            sleep(period)
    t = threading.Thread(target=f)
    t.daemon = True
    t.start()

cron(env.update_global_stats_every, lambda: utils.update_global_stats(website))
cron(env.check_db_every, website.db.self_check, True)


# Website Algorithm
# =================

def add_stuff_to_context(request):
    request.context['username'] = None

    def filter_profile_subnav(user, participant, pages):
        out = []
        for foo, bar, show_them, show_others in pages:
            if (user.participant == participant and show_them) \
            or (user.participant is None and show_others)       \
            or (user.participant != participant and show_others) \
            or user.ADMIN:
                out.append((foo, bar, show_them, show_others))
        return out
    request.context['filter_profile_subnav'] = filter_profile_subnav


    # Helpers for global call to action to support Gratipay itself.
    user = request.context.get('user')
    p = user.participant if user else None
    if p and p.is_free_rider is None:
        usage = p.usage

        # Above $500/wk we suggest 2%.
        if usage >= 5000:
            low = D('100.00')
            high = D('1000.00')
        elif usage >= 500:
            low = D('10.00')
            high = D('100.00')

        # From $20 to $499 we suggest 5%.
        elif usage >= 100:
            low = D('5.00')
            high = D('25.00')
        elif usage >= 20:
            low = D('1.00')
            high = D('5.00')

        # Below $20 we suggest 10%.
        elif usage >= 5:
            low = D('0.50')
            high = D('2.00')
        else:
            low = D('0.10')
            high = D('1.00')

        request.context['cta_low'] = low
        request.context['cta_high'] = high


noop = lambda: None
algorithm = website.algorithm
algorithm.functions = [ timer.start
                      , algorithm['parse_environ_into_request']
                      , algorithm['parse_body_into_request']
                      , algorithm['raise_200_for_OPTIONS']

                      , canonize
                      , authentication.get_auth_from_request
                      , csrf.get_csrf_token_from_request
                      , add_stuff_to_context
                      , i18n.set_up_i18n

                      , algorithm['dispatch_request_to_filesystem']

                      , cache_static.get_etag_for_file if website.cache_static else noop
                      , cache_static.try_to_serve_304 if website.cache_static else noop

                      , algorithm['apply_typecasters_to_path']
                      , algorithm['get_resource_for_request']
                      , algorithm['get_response_for_resource']

                      , tell_sentry
                      , algorithm['get_response_for_exception']

                      , gratipay.set_misc_headers
                      , authentication.add_auth_to_response
                      , csrf.add_csrf_token_to_response
                      , cache_static.add_caching_to_response if website.cache_static else noop
                      , x_frame_options

                      , algorithm['log_traceback_for_5xx']
                      , algorithm['delegate_error_to_simplate']
                      , tell_sentry
                      , algorithm['log_traceback_for_exception']
                      , algorithm['log_result_of_request']

                      , timer.end
                      , tell_sentry
                       ]
