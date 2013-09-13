import locale
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
gittip.wireup.sentry(website)
gittip.wireup.mixpanel(website)
gittip.wireup.nanswers()
gittip.wireup.nmembers(website)
gittip.wireup.envvars(website)


# Up the threadpool size: https://github.com/gittip/www.gittip.com/issues/1098
def up_minthreads(website):
    # Discovered the following API by inspecting in pdb and browsing source.
    # This requires network_engine.bind to have already been called.
    website.network_engine.cheroot_server.requests.min = \
                                                 int(os.environ['MIN_THREADS'])

website.hooks.startup.insert(0, up_minthreads)


website.hooks.inbound_early += [ gittip.canonize
                               , gittip.configure_payments
                               , gittip.security.authentication.inbound
                               , gittip.security.csrf.inbound
                                ]

website.hooks.inbound_late += [ gittip.utils.cache_static.inbound
                              #, gittip.security.authentication.check_role
                              #, participant.typecast
                              #, community.typecast
                               ]

website.hooks.outbound += [ gittip.security.authentication.outbound
                          , gittip.security.csrf.outbound
                          , gittip.utils.cache_static.outbound
                           ]


# X-Frame-Origin
# ==============
# This is a security measure to prevent clickjacking:
# http://en.wikipedia.org/wiki/Clickjacking

def x_frame_options(response):
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

website.hooks.outbound += [x_frame_options]


def add_stuff(request):
    from gittip.elsewhere import bitbucket, github, twitter, bountysource
    request.context['username'] = None
    request.context['bitbucket'] = bitbucket
    request.context['github'] = github
    request.context['twitter'] = twitter
    request.context['bountysource'] = bountysource
    stats = gittip.db.one( "SELECT nactive, transfer_volume FROM paydays "
                           "ORDER BY ts_end DESC LIMIT 1"
                         , default=(0, 0.0)
                          )
    request.context['gnactive'] = locale.format("%d", round(stats[0], -2), grouping=True)
    request.context['gtransfer_volume'] = locale.format("%d", round(stats[1], -2), grouping=True)

website.hooks.inbound_early += [add_stuff]


# The homepage wants expensive queries. Let's periodically select into an
# intermediate table.

UPDATE_HOMEPAGE_EVERY = int(os.environ['UPDATE_HOMEPAGE_EVERY'])
def update_homepage_queries():
    from gittip import utils
    while 1:
        utils.update_homepage_queries_once(website.db)
        time.sleep(UPDATE_HOMEPAGE_EVERY)

homepage_updater = threading.Thread(target=update_homepage_queries)
homepage_updater.daemon = True
homepage_updater.start()
