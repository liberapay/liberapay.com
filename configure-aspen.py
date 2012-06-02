import os

import gittip 
import gittip.wireup
import gittip.authentication


gittip.wireup.canonical()
gittip.wireup.db()
gittip.wireup.samurai()

website.github_client_id = os.environ['GITHUB_CLIENT_ID']
website.github_client_secret = os.environ['GITHUB_CLIENT_SECRET']
website.github_callback = os.environ['GITHUB_CALLBACK']

website.hooks.inbound_early.register(gittip.canonize) 
website.hooks.inbound_early.register(gittip.authentication.inbound) 
website.hooks.outbound_late.register(gittip.authentication.outbound) 

def add_stuff(request):
    request.context['__version__'] = gittip.__version__
    request.context['username'] = None 

website.hooks.inbound_early.register(add_stuff) 
