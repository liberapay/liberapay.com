from aspen.utils import typecheck
from tornado.escape import linkify


def wrap(u):
    """Given a unicode, return a unicode.
    """
    typecheck(u, unicode)
    u = linkify(u)  # Do this first, because it calls xthml_escape.
    u = u.replace(u'\r\n', u'<br />\r\n').replace(u'\n', u'<br />\n')
    return u if u else '...'


