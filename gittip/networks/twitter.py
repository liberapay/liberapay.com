import requests
from aspen import json, log, Response
from gittip import db, networks


def upsert(user_info):
    return networks.upsert( 'twitter'
                          , user_info['id']
                          , user_info['screen_name']
                          , user_info
                           )


def oauth_dance(website, qs):
    """Given a querystring, return a dict of user_info.

    The querystring should be the querystring that we get from Twitter when
    we send the user to the return value of oauth_url above.

    See also:

        http://developer.twitter.com/v3/oauth/

    """

    log("Doing an OAuth dance with Twitter.")

    if 'denied' in qs:
        raise Response(500, str(qs['denied']))

    data = { 'code': qs['code'].encode('US-ASCII')
           , 'client_id': website.twitter_customer_key
           , 'client_secret': website.twitter_customer_secret
            }
    r = requests.post("https://api.twitter.com/oauth/access_token", data=data)
    assert r.status_code == 200, (r.status_code, r.text)

    back = dict([pair.split('=') for pair in r.text.split('&')]) # XXX
    if 'error' in back:
        raise Response(400, back['error'].encode('utf-8'))
    assert back.get('token_type', '') == 'bearer', back
    access_token = back['access_token']

    r = requests.get( "https://api.twitter.com/user"
                    , headers={'Authorization': 'token %s' % access_token}
                     )
    assert r.status_code == 200, (r.status_code, r.text)
    user_info = json.loads(r.text)
    log("Done with OAuth dance with Twitter for %s (%s)."
        % (user_info['login'], user_info['id']))

    return user_info


def resolve(user_id):
    """Given str, return a participant_id.
    """
    FETCH = """\

        SELECT participant_id
          FROM social_network_users
         WHERE network='twitter'
           AND user_info -> 'user_id' = %s

    """ # XXX Uniqueness constraint on screen_name?
    rec = db.fetchone(FETCH, (user_id,))
    if rec is None:
        raise Exception("Twitter user %s has no participant." % (user_id))
    return rec['participant_id']
