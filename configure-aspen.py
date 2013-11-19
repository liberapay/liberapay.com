from __future__ import division

import os
import threading
import time

import gittip
import gittip.wireup
import gittip.security.authentication
import gittip.security.csrf
import gittip.utils.cache_static


version_file = os.path.join(website.www_root, 'version.txt')
__version__ = open(version_file).read().strip()
website.version = os.environ['__VERSION__'] = __version__


website.renderer_default = "tornado"


gittip.wireup.canonical()
website.db = gittip.wireup.db()
gittip.wireup.billing()
gittip.wireup.username_restrictions(website)
gittip.wireup.mixpanel(website)
gittip.wireup.nanswers()
gittip.wireup.nmembers(website)
gittip.wireup.envvars(website)
tell_sentry = gittip.wireup.make_sentry_teller(website)

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


# The homepage wants expensive queries. Let's periodically select into an
# intermediate table.

UPDATE_HOMEPAGE_EVERY = int(os.environ['UPDATE_HOMEPAGE_EVERY'])
def update_homepage_queries():
    from gittip import utils
    while 1:
        try:
            utils.update_global_stats(website)
            utils.update_homepage_queries_once(website.db)
        except:
            tell_sentry(None)
        time.sleep(UPDATE_HOMEPAGE_EVERY)

homepage_updater = threading.Thread(target=update_homepage_queries)
homepage_updater.daemon = True
homepage_updater.start()


# Algorithm
# =========
from gittip import canonize
from gittip import configure_payments
from gittip.security import authentication, csrf
from gittip.utils import cache_static


def start_timer():
    return {'start_time': time.time()}

def log_request_count_and_response_time(start_time):
    print("count#requests=1")
    response_time = time.time() - start_time
    print("measure#response_time={}ms".format(response_time * 1000))

def add_stuff_to_context(request):
    from gittip.elsewhere import bitbucket, github, twitter, bountysource
    request.context['username'] = None
    request.context['bitbucket'] = bitbucket
    request.context['github'] = github
    request.context['twitter'] = twitter
    request.context['bountysource'] = bountysource

def x_frame_options(response):
    """ X-Frame-Origin

    This is a security measure to prevent clickjacking:
    http://en.wikipedia.org/wiki/Clickjacking

    """
    if 'X-Frame-Options' not in response.headers:
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    elif response.headers['X-Frame-Options'] == 'ALLOWALL':

        # ALLOWALL is non-standard. It's useful as a signal from a simplate
        # that it doesn't want X-Frame-Options set at all, but because it's
        # non-standard we don't send it. Instead we unset the header entirely,
        # which has the desired effect of allowing framing indiscriminately.
        #
        # Refs.:
        #
        #   http://en.wikipedia.org/wiki/Clickjacking#X-Frame-Options
        #   http://ipsec.pl/node/1094

        del response.headers['X-Frame-Options']


website.algorithm.functions = [ website.algorithm.get_function('parse_environ_into_request')

                              , start_timer

                              , website.algorithm.get_function('tack_website_onto_request')
                              , website.algorithm.get_function('raise_200_for_OPTIONS')

                              , canonize
                              , configure_payments
                              , authentication.inbound
                              , csrf.inbound
                              , add_stuff_to_context

                              , website.algorithm.get_function('dispatch_request_to_filesystem')

                              , cache_static.inbound

                              , website.algorithm.get_function('get_response_for_socket')
                              , website.algorithm.get_function('get_response_for_resource')
                              , website.algorithm.get_function('get_response_for_exception')

                              , authentication.outbound
                              , csrf.outbound
                              , cache_static.outbound
                              , x_frame_options

                              , website.algorithm.get_function('log_traceback_for_5xx')
                              , website.algorithm.get_function('delegate_error_to_simplate')
                              , website.algorithm.get_function('log_traceback_for_exception')
                              , website.algorithm.get_function('log_result_of_request')

                              , log_request_count_and_response_time
                               ]
