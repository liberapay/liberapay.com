"""Defines website authentication helpers.
"""
import binascii

from six.moves.urllib.parse import urlencode

from pando import Response

from liberapay.constants import SESSION, SESSION_TIMEOUT
from liberapay.exceptions import AuthRequired
from liberapay.models.participant import Participant


class _ANON(object):
    ANON = True
    is_admin = False
    id = None
    __bool__ = __nonzero__ = lambda *a: False
    get_tip_to = lambda self, tippee: Participant._zero_tip_dict(tippee)
    __repr__ = lambda self: '<ANON>'


ANON = _ANON()


def _get_body(request):
    try:
        body = request.body
    except Response:
        return
    if not isinstance(body, dict):
        return
    return body


def sign_in_with_form_data(body, state):
    p = None
    _, website = state['_'], state['website']

    if body.get('log-in.id'):
        id = body.pop('log-in.id')
        k = 'email' if '@' in id else 'username'
        p = Participant.authenticate(
            k, 'password',
            id, body.pop('log-in.password')
        )
        if not p:
            state['sign-in.error'] = _("Bad username or password.")
        if p and p.status == 'closed':
            p.update_status('active')

    elif body.get('sign-in.username'):
        if body.pop('sign-in.terms') != 'agree':
            raise Response(400, 'you have to agree to the terms')
        kind = body.pop('sign-in.kind')
        if kind not in ('individual', 'organization'):
            raise Response(400, 'bad kind')
        with website.db.get_cursor() as c:
            p = Participant.make_active(
                body.pop('sign-in.username'), kind, body.pop('sign-in.password'),
                cursor=c
            )
            p.add_email(body.pop('sign-in.email'), cursor=c)
        p.authenticated = True

    elif body.get('email-login.email'):
        email = body.pop('email-login.email')
        p = Participant._from_thing('email', email)
        if p:
            p.start_session()
            qs = {'log-in.id': p.id, 'log-in.token': p.session_token}
            p.send_email(
                'password_reset',
                email=email,
                link=p.url('settings/', qs),
                link_validity=SESSION_TIMEOUT,
            )
            state['email-login.sent-to'] = email
        else:
            state['sign-in.error'] = _(
                "We didn't find any account whose primary email address is {0}.",
                email
            )
        p = None

    return p


def start_user_as_anon():
    """Make sure we always have a user object, regardless of exceptions during authentication.
    """
    return {'user': ANON}


def authenticate_user_if_possible(request, state, user, _):
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
    session_p, p = p, None
    session_suffix = ''
    redirect_url = request.line.uri
    if request.method == 'POST':
        body = _get_body(request)
        if body:
            p = sign_in_with_form_data(body, state)
            carry_on = body.pop('email-login.carry-on', None)
            if not p and carry_on:
                p_email = session_p and (
                    session_p.email or session_p.get_emails()[0].address
                )
                if p_email != carry_on:
                    state['email-login.carry-on'] = carry_on
                    raise AuthRequired
            redirect_url = body.get('sign-in.back-to') or redirect_url
    elif request.method == 'GET' and request.qs.get('log-in.id'):
        id, token = request.qs.pop('log-in.id'), request.qs.pop('log-in.token')
        p = Participant.authenticate('id', 'session', id, token)
        if not p and (not session_p or session_p.id != id):
            raise Response(400, _("This login link is expired or invalid."))
        else:
            qs = '?' + urlencode(request.qs, doseq=True) if request.qs else ''
            redirect_url = request.path.raw + qs
            session_p = p
            session_suffix = '.em'
    if p:
        if session_p:
            session_p.sign_out(response.headers.cookie)
        p.sign_in(response.headers.cookie, session_suffix)
        state['user'] = p
        if request.body.pop('form.repost', None) != 'true':
            response.redirect(redirect_url)


def add_auth_to_response(response, request=None, user=ANON):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith('/assets/'):
        return  # assets never get auth headers

    if SESSION in request.headers.cookie:
        if not user.ANON:
            user.keep_signed_in(response.headers.cookie)
