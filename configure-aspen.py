import os

import logstown 
import logstown.authentication


logstown.wire_canonical()
logstown.wire_db()
logstown.wire_samurai()

website.github_client_id = os.environ['GITHUB_CLIENT_ID']
website.github_client_secret = os.environ['GITHUB_CLIENT_SECRET']

website.hooks.inbound_early.register(logstown.authentication.inbound) 
website.hooks.outbound_late.register(logstown.authentication.outbound) 

def add_stuff(request):
    request.context['__version__'] = "dev"
    request.context['username'] = None 

website.hooks.inbound_early.register(add_stuff) 
