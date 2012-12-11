import os

import gittip
import gittip.wireup
import gittip.authentication
import gittip.orm
import gittip.csrf


gittip.wireup.canonical()
gittip.wireup.db()
gittip.wireup.billing()
gittip.wireup.id_restrictions(website)


website.github_client_id = os.environ['GITHUB_CLIENT_ID'].decode('ASCII')
website.github_client_secret = os.environ['GITHUB_CLIENT_SECRET'].decode('ASCII')
website.github_callback = os.environ['GITHUB_CALLBACK'].decode('ASCII')

website.twitter_consumer_key = os.environ['TWITTER_CONSUMER_KEY'].decode('ASCII')
website.twitter_consumer_secret = os.environ['TWITTER_CONSUMER_SECRET'].decode('ASCII')
website.twitter_callback = os.environ['TWITTER_CALLBACK'].decode('ASCII')

website.hooks.inbound_early.register(gittip.canonize)
website.hooks.inbound_early.register(gittip.configure_payments)
website.hooks.inbound_early.register(gittip.csrf.inbound)
website.hooks.inbound_early.register(gittip.authentication.inbound)
website.hooks.outbound_late.register(gittip.authentication.outbound)
website.hooks.outbound_late.register(gittip.csrf.outbound)
website.hooks.outbound_late.register(gittip.orm.rollback)


__version__ = open(os.path.join(website.www_root, 'version.txt')).read().strip()


def add_stuff(request):
    from gittip.elsewhere import github, twitter
    request.context['__version__'] = __version__
    request.context['username'] = None
    request.context['github'] = github
    request.context['twitter'] = twitter

website.hooks.inbound_early.register(add_stuff)
