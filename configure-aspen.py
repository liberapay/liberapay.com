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
from gittip.utils import cache_static, set_cookie, timer


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

def update_homepage_queries():
    utils.update_global_stats(website)
    utils.update_homepage_queries_once(website.db)

cron(env.update_homepage_every, update_homepage_queries)

cron(env.check_db_every, website.db.self_check)


# Server Algorithm
# ================

def up_minthreads(website):
    # https://github.com/gittip/www.gittip.com/issues/1098
    # Discovered the following API by inspecting in pdb and browsing source.
    # This requires network_engine.bind to have already been called.
    request_queue = website.network_engine.cheroot_server.requests
    request_queue.min = website.min_threads


def setup_busy_threads_logging(website):
    # https://github.com/gittip/www.gittip.com/issues/1572
    log_every = website.log_busy_threads_every
    if log_every == 0:
        return

    pool = website.network_engine.cheroot_server.requests
    def log_busy_threads():
        time.sleep(0.5)  # without this we get a single log message where all threads are busy
        while 1:

            # Use pool.min and not pool.max because of the semantics of these
            # inside of Cheroot. (Max is a hard limit used only when pool.grow
            # is called, and it's never called except when the pool starts up,
            # when it's called with pool.min.)

            nbusy_threads = pool.min - pool.idle
            print("sample#aspen.busy_threads={}".format(nbusy_threads))
            time.sleep(log_every)

    thread = threading.Thread(target=log_busy_threads)
    thread.daemon = True
    thread.start()


website.server_algorithm.insert_before('start', up_minthreads)
website.server_algorithm.insert_before('start', setup_busy_threads_logging)


# Website Algorithm
# =================

def add_stuff_to_context(request):
    request.context['username'] = None

def scab_body_onto_response(response):

    # This is a workaround for a Cheroot bug, where the connection is closed
    # too early if there is no body:
    #
    # https://bitbucket.org/cherrypy/cheroot/issue/1/fail-if-passed-zero-bytes
    #
    # This Cheroot bug is manifesting because of a change in Aspen's behavior
    # with the algorithm.py refactor in 0.27+: Aspen no longer sets a body for
    # 302s as it used to. This means that all redirects are breaking
    # intermittently (sometimes the client seems not to care that the
    # connection is closed too early, so I guess there's some timing
    # involved?), which is affecting a number of parts of Gittip, notably
    # around logging in (#1859).

    if not response.body:
        response.body = '*sigh*'


algorithm = website.algorithm
algorithm.functions = [ timer.start
                      , algorithm['parse_environ_into_request']
                      , algorithm['tack_website_onto_request']
                      , algorithm['raise_200_for_OPTIONS']

                      , canonize
                      , authentication.inbound
                      , csrf.inbound
                      , add_stuff_to_context

                      , algorithm['dispatch_request_to_filesystem']
                      , algorithm['apply_typecasters_to_path']

                      , cache_static.inbound

                      , algorithm['get_response_for_socket']
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

                      , scab_body_onto_response
                      , timer.end
                      , tell_sentry
                       ]
