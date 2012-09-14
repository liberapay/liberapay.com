from gittip import db, networks


def upsert(user_info):
    return networks.upsert( 'twitter'
                          , user_info['id']
                          , user_info['screen_name']
                          , user_info
                           )


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


def oauth_url(website, action, then):
    return "/on/twitter/redirect?action=%s&then=%s" % (action, then)
