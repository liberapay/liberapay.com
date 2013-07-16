import os

import gittip
import gittip.wireup
import gittip.authentication
import gittip.orm
import gittip.csrf
import gittip.cache_static
import gittip.models.participant


gittip.wireup.canonical()
gittip.wireup.db()
gittip.wireup.billing()
gittip.wireup.username_restrictions(website)
gittip.wireup.sentry(website)
gittip.wireup.mixpanel(website)
gittip.wireup.nanswers()
gittip.wireup.nmembers(website)


website.bitbucket_consumer_key = os.environ['BITBUCKET_CONSUMER_KEY'].decode('ASCII')
website.bitbucket_consumer_secret = os.environ['BITBUCKET_CONSUMER_SECRET'].decode('ASCII')
website.bitbucket_callback = os.environ['BITBUCKET_CALLBACK'].decode('ASCII')

website.github_client_id = os.environ['GITHUB_CLIENT_ID'].decode('ASCII')
website.github_client_secret = os.environ['GITHUB_CLIENT_SECRET'].decode('ASCII')
website.github_callback = os.environ['GITHUB_CALLBACK'].decode('ASCII')

website.twitter_consumer_key = os.environ['TWITTER_CONSUMER_KEY'].decode('ASCII')
website.twitter_consumer_secret = os.environ['TWITTER_CONSUMER_SECRET'].decode('ASCII')
website.twitter_access_token = os.environ['TWITTER_ACCESS_TOKEN'].decode('ASCII')
website.twitter_access_token_secret = os.environ['TWITTER_ACCESS_TOKEN_SECRET'].decode('ASCII')
website.twitter_callback = os.environ['TWITTER_CALLBACK'].decode('ASCII')

website.bountysource_www_host = os.environ['BOUNTYSOURCE_WWW_HOST'].decode('ASCII')
website.bountysource_api_host = os.environ['BOUNTYSOURCE_API_HOST'].decode('ASCII')
website.bountysource_api_secret = os.environ['BOUNTYSOURCE_API_SECRET'].decode('ASCII')
website.bountysource_callback = os.environ['BOUNTYSOURCE_CALLBACK'].decode('ASCII')


# Up the threadpool size: https://github.com/gittip/www.gittip.com/issues/1098
def up_minthreads(website):
    # Discovered the following API by inspecting in pdb and browsing source.
    # This requires network_engine.bind to have already been called.
    website.network_engine.cheroot_server.requests.min = int(os.environ['MIN_THREADS'])

website.hooks.startup.insert(0, up_minthreads)


website.hooks.inbound_early += [ gittip.canonize
                               , gittip.configure_payments
                               , gittip.authentication.inbound
                               , gittip.csrf.inbound
                                ]

#website.hooks.inbound_core += [gittip.cache_static.inbound]

website.hooks.outbound += [ gittip.authentication.outbound
                          , gittip.csrf.outbound
                          , gittip.orm.rollback
                          , gittip.cache_static.outbound
                           ]


__version__ = open(os.path.join(website.www_root, 'version.txt')).read().strip()
os.environ['__VERSION__'] = __version__


def add_stuff(request):
    from gittip.elsewhere import bitbucket, github, twitter, bountysource
    from gittip.utils import with_mine
    request.context['__version__'] = __version__
    request.context['username'] = None
    request.context['bitbucket'] = bitbucket
    request.context['github'] = github
    request.context['twitter'] = twitter
    request.context['bountysource'] = bountysource
    request.context['with_mine'] = with_mine

website.hooks.inbound_early += [add_stuff]
