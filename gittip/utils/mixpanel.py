"""Implement a Mixpanel wrapper.

Mixpanel doesn't maintain a Python library. Their docs show you how to use cURL
via subprocess(!):

    https://mixpanel.com/docs/integration-libraries/python

They try to steer you towards their JavaScript library. Now, you're supposed to
"do your best to only call alias once on each new user."

    https://mixpanel.com/docs/integration-libraries/using-mixpanel-alias

The trouble is that we don't have a single landing page when a user registers.
Instead we redirect them back to the page they were on or possibly elsewhere.
Rather than trying to signal to gittip.js somehow that it should alias the
user, we simply do the aliasing server-side. For tracking we still use the
JavaScript library.

I thought about implementing the HTTP call in a thread with a queue, but
decided to keep it simple for now. What happens when a client-side track call
happens before a server-side alias call lands, for example?

"""
from __future__ import unicode_literals

from Cookie import SimpleCookie
from urllib import unquote

import requests
from aspen import json
from aspen.utils import typecheck


MIXPANEL_TOKEN = None
session = requests.session()


def alias_and_track(cookie, gittip_user_id):
    """Given a cookie and a unicode, hit Mixpanel in a thread.
    """
    typecheck(cookie, SimpleCookie, gittip_user_id, unicode)

    # Pull distinct_id out of Mixpanel cookie. Yay undocumented internals!
    # This is bound to fail some day. Since this is in a thread, it shouldn't
    # affect the user experience, and we'll still get a record of the failure
    # in Sentry.

    mpcookie = [v for k, v in cookie.items() if k.endswith('_mixpanel')]
    if mpcookie:
        distinct_id = json.loads(unquote(mpcookie[0].value))['distinct_id']
        distinct_id = distinct_id.decode("utf8")
        alias(distinct_id, gittip_user_id)

    track(gittip_user_id, u"Opt In")


def alias(mixpanel_user_id, gittip_user_id):
    track(mixpanel_user_id, "$create_alias", {"alias": gittip_user_id})


def track(user_id, event, properties=None):
    if MIXPANEL_TOKEN is None:
        return

    typecheck(user_id, unicode, event, unicode, properties, (None, dict))
    if properties is None:
        properties = {}
    properties['token'] = MIXPANEL_TOKEN
    properties['distinct_id'] = user_id
    data = {"event": event, "properties": properties}
    data = json.dumps(data).encode("base64")
    #response = session.get("http://api.mixpanel.com/track?data=" + data)
    response = session.get("http://api.mixpanel.com/track",
                           params={'data': data})

    # Read response.content to take advantage of keep-alive. See:
    # http://docs.python-requests.org/en/latest/user/advanced/#keep-alive
    response.content
