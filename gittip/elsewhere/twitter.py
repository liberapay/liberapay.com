from gittip.elsewhere import AccountElsewhere, _resolve


class TwitterAccount(AccountElsewhere):
    platform = 'twitter'


def resolve(screen_name):
    return _resolve(u'twitter', u'screen_name', screen_name)


def oauth_url(website, action, then=""):
    """Return a URL to start oauth dancing with Twitter.

    For GitHub we can pass action and then through a querystring. For Twitter
    we can't, so we send people through a local URL first where we stash this
    info in an in-memory cache (eep! needs refactoring to scale).

    Not sure why website is here. Vestige from GitHub forebear?

    """
    return "/on/twitter/redirect?action=%s&then=%s" % (action, then)
