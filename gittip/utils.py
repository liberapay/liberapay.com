from aspen import Response
from aspen.utils import typecheck
from tornado.escape import linkify
from gittip.models.participant import Participant


def wrap(u):
    """Given a unicode, return a unicode.
    """
    typecheck(u, unicode)
    u = linkify(u)  # Do this first, because it calls xthml_escape.
    u = u.replace(u'\r\n', u'<br />\r\n').replace(u'\n', u'<br />\n')
    return u if u else '...'


def get_participant(request, restrict=True):
    """Given a Request, raise Response or return Participant.

    If user is not None then we'll restrict access to owners and admins.

    """
    user = request.context['user']
    if restrict:
        if user.ANON:
            raise Response(404)

    participant_id = request.line.uri.path['participant_id']
    participant = Participant.query.get(participant_id)

    if participant is None:
        raise Response(404)

    elif participant.claimed_time is None:

        # This is a stub participant record for someone on another platform who
        # hasn't actually registered with Gittip yet. Let's bounce the viewer
        # over to the appropriate platform page.

        to = participant.resolve_unclaimed()
        if to is None:
            raise Response(404)
        request.redirect(to)

    if restrict:
        if participant != user:
            if not user.ADMIN:
                raise Response(403)

    return participant
