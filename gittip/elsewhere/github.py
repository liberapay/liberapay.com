import requests
from aspen import json, log, Response
from aspen.website import Website
from aspen.utils import typecheck
from gittip import db, elsewhere


def upsert(user_info):
    return elsewhere.upsert( 'github'
                           , user_info['id']
                           , user_info['login']
                           , user_info
                            )


def oauth_url(website, action, then=u""):
    """Given a website object and a string, return a URL string.

    `action' is one of 'opt-in', 'lock' and 'unlock'

    `then' is either a github username or an URL starting with '/'. It's
        where we'll send the user after we get the redirect back from
        GitHub.

    """
    typecheck(website, Website, action, unicode, then, unicode)
    assert action in [u'opt-in', u'lock', u'unlock']
    url = u"https://github.com/login/oauth/authorize?client_id=%s&redirect_uri=%s"
    url %= (website.github_client_id, website.github_callback)

    # Pack action,then into data and base64-encode. Querystring isn't
    # available because it's consumed by the initial GitHub request.

    data = u'%s,%s' % (action, then)
    data = data.encode('UTF-8').encode('base64').decode('US-ASCII')
    url += u'?data=%s' % data
    return url


def oauth_dance(website, qs):
    """Given a querystring, return a dict of user_info.

    The querystring should be the querystring that we get from GitHub when
    we send the user to the return value of oauth_url above.

    See also:

        http://developer.github.com/v3/oauth/

    """

    log("Doing an OAuth dance with Github.")

    if 'error' in qs:
        raise Response(500, str(qs['error']))

    data = { 'code': qs['code'].encode('US-ASCII')
           , 'client_id': website.github_client_id
           , 'client_secret': website.github_client_secret
            }
    r = requests.post("https://github.com/login/oauth/access_token", data=data)
    assert r.status_code == 200, (r.status_code, r.text)

    back = dict([pair.split('=') for pair in r.text.split('&')]) # XXX
    if 'error' in back:
        raise Response(400, back['error'].encode('utf-8'))
    assert back.get('token_type', '') == 'bearer', back
    access_token = back['access_token']

    r = requests.get( "https://api.github.com/user"
                    , headers={'Authorization': 'token %s' % access_token}
                     )
    assert r.status_code == 200, (r.status_code, r.text)
    user_info = json.loads(r.text)
    log("Done with OAuth dance with Github for %s (%s)."
        % (user_info['login'], user_info['id']))

    return user_info


def resolve(login):
    """Given two str, return a participant_id.
    """
    FETCH = """\

        SELECT participant_id
          FROM social_network_users
         WHERE network='github'
           AND user_info -> 'login' = %s

    """ # XXX Uniqueness constraint on login?
    rec = db.fetchone(FETCH, (login,))
    if rec is None:
        raise Exception("GitHub user %s has no participant." % (login))
    return rec['participant_id']
