from gittip import db, elsewhere


def upsert(user_info):
    return elsewhere.upsert( 'twitter'
                           , user_info['id']
                           , user_info['screen_name']
                           , user_info
                            )


def resolve(user_id):
    """Given str, return a participant_id.
    """
    FETCH = """\

        SELECT participant_id
          FROM elsewhere
         WHERE platform='twitter'
           AND user_info -> 'user_id' = %s

    """ # XXX Uniqueness constraint on screen_name?
    rec = db.fetchone(FETCH, (user_id,))
    if rec is None:
        raise Exception("Twitter user %s has no participant." % (user_id))
    return rec['participant_id']


def oauth_url(website, action, then=""):
    """Return a URL to start oauth dancing with Twitter.

    For GitHub we can pass action and then through a querystring. For Twitter
    we can't, so we send people through a local URL first where we stash this
    info in an in-memory cache (eep! needs refactoring to scale).

    Not sure why website is here. Vestige from GitHub forebear?

    """
    return "/on/twitter/redirect?action=%s&then=%s" % (action, then)
