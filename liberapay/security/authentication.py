"""Defines website authentication helpers.
"""
import binascii

from aspen import Response
from liberapay.constants import SESSION
from liberapay.models.participant import Participant


class _ANON(object):
    ANON = True
    is_admin = False
    id = None
    __bool__ = __nonzero__ = lambda *a: False
    get_tip_to = lambda self, tippee: Participant._zero_tip_dict(tippee)
    __repr__ = lambda self: '<ANON>'


ANON = _ANON()


def sign_in_with_form_data(request, state):
    try:
        body = request.body
    except Response:
        return

    p = None

    if body.get('log-in.username'):
        p = Participant.authenticate(
            'username', 'password',
            body.pop('log-in.username'), body.pop('log-in.password')
        )
        if p and p.status == 'closed':
            p.update_status('active')

    elif body.get('sign-in.username'):
        if body.pop('sign-in.terms') != 'agree':
            raise Response(400, 'you have to agree to the terms')
        kind = body.pop('sign-in.kind')
        if kind not in ('individual', 'organization'):
            raise Response(400, 'bad kind')
        with state['website'].db.get_cursor() as c:
            p = Participant.make_active(
                body.pop('sign-in.username'), kind, body.pop('sign-in.password'),
                cursor=c
            )
            p.add_email(body.pop('sign-in.email'), cursor=c)
        p.authenticated = True

    return p


def start_user_as_anon():
    """Make sure we always have a user object, regardless of exceptions during authentication.
    """
    return {'user': ANON}


def authenticate_user_if_possible(request, state, user):
    """This signs the user in.
    """
    if request.line.uri.startswith('/assets/'):
        return

    # HTTP auth
    if 'Authorization' in request.headers:
        header = request.headers['authorization']
        if not header.startswith('Basic '):
            raise Response(401, 'Unsupported authentication method')
        try:
            creds = binascii.a2b_base64(header[len('Basic '):]).split(':', 1)
        except binascii.Error:
            raise Response(400, 'Malformed "Authorization" header')
        participant = Participant.authenticate('id', 'password', *creds)
        if not participant:
            raise Response(401)
        return {'user': participant}

    # Cookie and form auth
    # We want to try cookie auth first, but we want form auth to supersede it
    p = None
    response = state.setdefault('response', Response())
    if SESSION in request.headers.cookie:
        creds = request.headers.cookie[SESSION].value.split(':', 1)
        p = Participant.authenticate('id', 'session', *creds)
        if p:
            state['user'] = p
    if request.method == 'POST':
        old_p = p
        p = sign_in_with_form_data(request, state)
        if p:
            if old_p:
                old_p.sign_out(response.headers.cookie)
            p.sign_in(response.headers.cookie)
            state['user'] = p
            if request.body.pop('form.repost', None) != 'true':
                response.redirect(request.line.uri)


def add_auth_to_response(response, request=None, user=ANON):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith('/assets/'):
        return  # assets never get auth headers

    if SESSION in request.headers.cookie:
        if not user.ANON:
            user.keep_signed_in(response.headers.cookie)
