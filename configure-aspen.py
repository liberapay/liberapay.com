from __future__ import division

import os
import sys
import threading
import time
import traceback

import gittip
import gittip.wireup
from gittip import canonize, utils
from gittip.security import authentication, csrf, x_frame_options
from gittip.utils import cache_static, i18n, set_cookie, timer


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

version_file = os.path.join(website.www_root, 'version.txt')
website.version = open(version_file).read().strip()


website.renderer_default = "jinja2"

website.renderer_factories['jinja2'].Renderer.global_context = {
    'range': range,
    'unicode': unicode,
    'enumerate': enumerate,
    'len': len,
    'float': float,
    'type': type,
    'str': str
}


env = website.env = gittip.wireup.env()
gittip.wireup.canonical(env)
website.db = gittip.wireup.db(env)
website.mail = gittip.wireup.mail(env)
gittip.wireup.billing(env)
gittip.wireup.username_restrictions(website)
gittip.wireup.nanswers(env)
gittip.wireup.other_stuff(website, env)
gittip.wireup.accounts_elsewhere(website, env)
tell_sentry = website.tell_sentry = gittip.wireup.make_sentry_teller(env)

# The homepage wants expensive queries. Let's periodically select into an
# intermediate table.

def cron(period, func):
    def f():
        if period <= 0:
            return
        sleep = time.sleep
        while 1:
            try:
                func()
            except Exception, e:
                tell_sentry(e)
                log_dammit(traceback.format_exc().strip())
            sleep(period)
    t = threading.Thread(target=f)
    t.daemon = True
    t.start()

cron(env.update_global_stats_every, lambda: utils.update_global_stats(website))
cron(env.check_db_every, website.db.self_check)


# Website Algorithm
# =================

def add_stuff_to_context(request):
    request.context['username'] = None

    # Helpers for global call to action to support Gittip itself.
    user = request.context.get('user')
    p = user.participant if user else None
    if p and p.is_free_rider is None:
        usage = p.usage

        # Above $500/wk we suggest 2%.
        if usage >= 5000:
            low = ('100.00', '$100')
            high = ('1000.00', '$1000')
        elif usage >= 500:
            low = ('10.00', '$10')
            high = ('100.00', '$100')

        # From $20 to $499 we suggest 5%.
        elif usage >= 100:
            low = ('5.00', '$5')
            high = ('25.00', '$25')
        elif usage >= 20:
            low = ('1.00', '$1')
            high = ('5.00', '$5')

        # Below $20 we suggest 10%.
        elif usage >= 5:
            low = ('0.50', '50&cent;')
            high = ('2.00', '$2.00')
        else:
            low = ('0.10', '10&cent;')
            high = ('1.00', '$1.00')

        request.context['cta_low'] = low
        request.context['cta_high'] = high


algorithm = website.algorithm
algorithm.functions = [ timer.start
                      , algorithm['parse_environ_into_request']
                      , algorithm['tack_website_onto_request']
                      , algorithm['raise_200_for_OPTIONS']

                      , canonize
                      , authentication.inbound
                      , csrf.inbound
                      , add_stuff_to_context
                      , i18n.inbound

                      , algorithm['dispatch_request_to_filesystem']
                      , algorithm['apply_typecasters_to_path']

                      , cache_static.inbound

                      , algorithm['get_resource_for_request']
                      , algorithm['get_response_for_resource']

                      , tell_sentry
                      , algorithm['get_response_for_exception']

                      , gittip.outbound
                      , authentication.outbound
                      , csrf.outbound
                      , cache_static.outbound
                      , x_frame_options

                      , algorithm['log_traceback_for_5xx']
                      , algorithm['delegate_error_to_simplate']
                      , tell_sentry
                      , algorithm['log_traceback_for_exception']
                      , algorithm['log_result_of_request']

                      , timer.end
                      , tell_sentry
                       ]
