"""Defines website authentication helpers.
"""

from urllib.parse import urlencode

from pando import Response

from liberapay.constants import (
    CURRENCIES, PASSWORD_MIN_SIZE, PASSWORD_MAX_SIZE, SESSION, SESSION_TIMEOUT
)
from liberapay.exceptions import (
    BadPasswordSize, EmailAlreadyTaken, LoginRequired,
    TooManyLogInAttempts, TooManyLoginEmails, TooManySignUps,
)
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.participant import Participant
from liberapay.security.crypto import constant_time_compare
from liberapay.utils import get_ip_net
from liberapay.utils.emails import check_email_blacklist, normalize_email_address


class _ANON(object):
    ANON = True
    is_admin = False
    session = None
    id = None
    __bool__ = __nonzero__ = lambda *a: False
    get_tip_to = staticmethod(Participant._zero_tip_dict)
    __repr__ = lambda self: '<ANON>'

    def get_currencies_for(self, tippee, tip):
        if isinstance(tippee, AccountElsewhere):
            tippee = tippee.participant
        return tip['amount'].currency, tippee.accepted_currencies_set


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
        request = state['request']
        src_addr, src_country = request.source, request.country
        website.db.hit_rate_limit('log-in.ip-addr', str(src_addr), TooManyLogInAttempts)
        website.db.hit_rate_limit('log-in.country', src_country, TooManyLogInAttempts)
        id = body.pop('log-in.id').strip()
        password = body.pop('log-in.password', None)
        k = 'email' if '@' in id else 'username'
        if password:
            id = Participant.get_id_for(k, id)
            p = Participant.authenticate(id, 0, password)
            if not p:
                state['log-in.error'] = _("Bad username or password.")
            else:
                try:
                    p.check_password(password, context='login')
                except Exception as e:
                    website.tell_sentry(e, state)

        elif k == 'username':
            state['log-in.error'] = _("\"{0}\" is not a valid email address.", id)
            return
        else:
            email = id
            p = Participant.from_email(email)
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
                qs = [
                    ('log-in.id', p.id),
                    ('log-in.key', p.session.id),
                    ('log-in.token', p.session.secret)
                ]
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
        # Check the submitted data
        kind = body.pop('sign-in.kind', 'individual')
        if kind not in ('individual', 'organization'):
            raise response.invalid_input(kind, 'sign-in.kind', 'body')
        email = body.pop('sign-in.email')
        if not email:
            raise response.error(400, 'email is required')
        email = normalize_email_address(email)
        check_email_blacklist(email)
        currency = body.pop('sign-in.currency', 'EUR')
        if currency not in CURRENCIES:
            raise response.invalid_input(currency, 'sign-in.currency', 'body')
        password = body.pop('sign-in.password', None)
        if password:
            l = len(password)
            if l < PASSWORD_MIN_SIZE or l > PASSWORD_MAX_SIZE:
                raise BadPasswordSize
        session_token = body.pop('sign-in.token', '')
        if session_token:
            Participant.check_session_token(session_token)
        # Check for an existing account
        existing_account = website.db.one("""
            SELECT p, s.secret
              FROM emails e
              JOIN participants p ON p.id = e.participant
              JOIN user_secrets s ON s.participant = p.id AND s.id = 1
             WHERE e.address = %s
               AND e.verified IS NULL
               AND p.join_time > (current_timestamp - interval '30 minutes')
        """, (email,))
        if existing_account:
            p, secret = existing_account
            if constant_time_compare(session_token, secret):
                p.authenticated = True
                p.sign_in(response.headers.cookie, token=session_token)
                return p
            else:
                raise EmailAlreadyTaken(email)
        # Rate limit
        request = state['request']
        src_addr, src_country = request.source, request.country
        website.db.hit_rate_limit('sign-up.ip-addr', str(src_addr), TooManySignUps)
        website.db.hit_rate_limit('sign-up.ip-net', get_ip_net(src_addr), TooManySignUps)
        website.db.hit_rate_limit('sign-up.country', src_country, TooManySignUps)
        website.db.hit_rate_limit('sign-up.ip-version', src_addr.version, TooManySignUps)
        # Okay, create the account
        with website.db.get_cursor() as c:
            p = Participant.make_active(
                kind, currency, body.pop('sign-in.username', None), cursor=c,
            )
            p.set_email_lang(state['locale'].language, cursor=c)
            p.add_email(email, cursor=c)
        if password:
            p.update_password(password)
            p.check_password(password, context='login')
        p.authenticated = True
        p.sign_in(response.headers.cookie, token=session_token)

    return p


def start_user_as_anon():
    """Make sure we always have a user object, regardless of exceptions during authentication.
    """
    return {'user': ANON}


def authenticate_user_if_possible(request, response, state, user, _):
    """This signs the user in.
    """
    if request.line.uri.startswith(b'/assets/'):
        return

    if not state['website'].db:
        return

    # Cookie and form auth
    # We want to try cookie auth first, but we want form auth to supersede it
    p = None
    if SESSION in request.headers.cookie:
        creds = request.headers.cookie[SESSION].value.split(':', 2)
        if len(creds) == 2:
            creds = [creds[0], 1, creds[1]]
        if len(creds) == 3:
            p = Participant.authenticate(*creds)
            if p:
                state['user'] = p
    session_p, p = p, None
    session_suffix = ''
    redirect_url = request.line.uri.decoded
    if request.method == 'POST':
        body = _get_body(request)
        if body:
            p = sign_in_with_form_data(body, state)
            carry_on = body.pop('log-in.carry-on', None)
            if not p and carry_on:
                p_email = session_p and (
                    session_p.email or session_p.get_any_email()
                )
                if p_email != carry_on:
                    state['log-in.carry-on'] = carry_on
                    raise LoginRequired
            redirect_url = body.get('sign-in.back-to') or redirect_url
    elif request.method == 'GET' and request.qs.get('log-in.id'):
        id = request.qs.pop('log-in.id')
        session_id = request.qs.pop('log-in.key', 1)
        token = request.qs.pop('log-in.token', None)
        p = Participant.authenticate(id, session_id, token)
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
        if not p.session:
            p.sign_in(response.headers.cookie, suffix=session_suffix)
        state['user'] = p
        if request.body.pop('form.repost', None) != 'true':
            response.redirect(redirect_url, trusted_url=False)


def add_auth_to_response(response, request=None, user=ANON):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith(b'/assets/'):
        return  # assets never get auth headers

    if SESSION in request.headers.cookie:
        if user.session:
            user.keep_signed_in(response.headers.cookie)
