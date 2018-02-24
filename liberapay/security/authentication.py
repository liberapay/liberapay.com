"""Defines website authentication helpers.
"""
import binascii

from six.moves.urllib.parse import urlencode

from pando import Response

from liberapay.constants import CURRENCIES, SESSION, SESSION_TIMEOUT
from liberapay.exceptions import (
    LoginRequired, TooManyLoginEmails, TooManySignUps
)
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.participant import Participant
from liberapay.utils import get_ip_net


class _ANON(object):
    ANON = True
    is_admin = False
    id = None
    __bool__ = __nonzero__ = lambda *a: False
    get_tip_to = staticmethod(Participant._zero_tip_dict)
    __repr__ = lambda self: '<ANON>'

    def get_currencies_for(self, tippee, tip):
        if isinstance(tippee, AccountElsewhere):
            tippee = tippee.participant
        return tip['amount'].currency, tippee.accepted_currencies


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
        id = body.pop('log-in.id').strip()
        password = body.pop('log-in.password', None)
        k = 'email' if '@' in id else 'username'
        if password:
            p = Participant.authenticate(
                k, 'password',
                id, password,
            )
            if not p:
                state['log-in.error'] = _("Bad username or password.")
        elif k == 'username':
            state['log-in.error'] = _("\"{0}\" is not a valid email address.", id)
            return
        else:
            email = id
            p = Participant._from_thing('lower(email)', email.lower())
            if p and p.kind == 'group':
                state['log-in.error'] = _(
                    "{0} is linked to a team account. It's not possible to log in as a team.",
                    email
                )
            elif p:
                if not p.get_email(email).verified:
                    website.db.hit_rate_limit('log-in.email.not-verified', email, TooManyLoginEmails)
                website.db.hit_rate_limit('log-in.email', p.id, TooManyLoginEmails)
                p.start_session()
                qs = {'log-in.id': p.id, 'log-in.token': p.session_token}
                p.send_email(
                    'login_link',
                    email,
                    link=p.url('settings/', qs),
                    link_validity=SESSION_TIMEOUT,
                )
                state['log-in.email-sent-to'] = email
                raise LoginRequired
            else:
                state['log-in.error'] = _(
                    "We didn't find any account whose primary email address is {0}.",
                    email
                )
            p = None

    elif 'sign-in.email' in body:
        response = state['response']
        kind = body.pop('sign-in.kind', 'individual')
        if kind not in ('individual', 'organization'):
            raise response.error(400, 'bad kind')
        email = body.pop('sign-in.email')
        if not email:
            raise response.error(400, 'email is required')
        currency = body.pop('sign-in.currency', 'EUR')
        if currency not in CURRENCIES:
            raise response.error(400, "`currency` value '%s' is invalid of non-supported" % currency)
        src_addr = state['request'].source
        website.db.hit_rate_limit('sign-up.ip-addr', str(src_addr), TooManySignUps)
        website.db.hit_rate_limit('sign-up.ip-net', get_ip_net(src_addr), TooManySignUps)
        website.db.hit_rate_limit('sign-up.ip-version', src_addr.version, TooManySignUps)
        with website.db.get_cursor() as c:
            p = Participant.make_active(
                kind, currency, body.pop('sign-in.username', None),
                body.pop('sign-in.password', None), cursor=c,
            )
            p.set_email_lang(state['locale'].language, cursor=c)
            p.add_email(email, cursor=c)
        p.authenticated = True

    return p


def start_user_as_anon():
    """Make sure we always have a user object, regardless of exceptions during authentication.
    """
    return {'user': ANON}


def authenticate_user_if_possible(request, response, state, user, _):
    """This signs the user in.
    """
    if request.line.uri.startswith('/assets/'):
        return

    if not state['website'].db:
        return

    # HTTP auth
    if b'Authorization' in request.headers:
        header = request.headers[b'Authorization']
        if not header.startswith(b'Basic '):
            raise response.error(401, 'Unsupported authentication method')
        try:
            uid, pwd = binascii.a2b_base64(header[len('Basic '):]).decode('utf8').split(':', 1)
        except (binascii.Error, UnicodeDecodeError, ValueError):
            raise response.error(400, 'Malformed "Authorization" header')
        if not uid.isdigit():
            raise response.error(401, 'Invalid user id: expected an integer, got `%s`' % uid)
        participant = Participant.authenticate('id', 'password', uid, pwd)
        if not participant:
            raise response.error(401, 'Invalid credentials')
        return {'user': participant}

    # Cookie and form auth
    # We want to try cookie auth first, but we want form auth to supersede it
    p = None
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
            carry_on = body.pop('log-in.carry-on', None)
            if not p and carry_on:
                p_email = session_p and (
                    session_p.email or session_p.get_emails()[0].address
                )
                if p_email != carry_on:
                    state['log-in.carry-on'] = carry_on
                    raise LoginRequired
            redirect_url = body.get('sign-in.back-to') or redirect_url
    elif request.method == 'GET' and request.qs.get('log-in.id'):
        id, token = request.qs.pop('log-in.id'), request.qs.pop('log-in.token')
        p = Participant.authenticate('id', 'session', id, token)
        if not p and (not session_p or session_p.id != id):
            raise response.error(400, _("This login link is expired or invalid."))
        else:
            qs = '?' + urlencode(request.qs, doseq=True) if request.qs else ''
            redirect_url = request.path.raw + qs
            session_p = p
            session_suffix = '.em'
    if p:
        if session_p:
            session_p.sign_out(response.headers.cookie)
        if p.status == 'closed':
            p.update_status('active')
        p.sign_in(response.headers.cookie, session_suffix)
        state['user'] = p
        if request.body.pop('form.repost', None) != 'true':
            response.redirect(redirect_url, trusted_url=False)


def add_auth_to_response(response, request=None, user=ANON):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith('/assets/'):
        return  # assets never get auth headers

    if SESSION in request.headers.cookie:
        if not user.ANON:
            user.keep_signed_in(response.headers.cookie)
