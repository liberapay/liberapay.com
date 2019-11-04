"""Defines website authentication helpers.
"""

from pando import Response

from liberapay.constants import (
    CURRENCIES, PASSWORD_MIN_SIZE, PASSWORD_MAX_SIZE, SESSION, SESSION_TIMEOUT
)
from liberapay.exceptions import (
    BadPasswordSize, EmailAlreadyTaken, LoginRequired,
    TooManyLogInAttempts, TooManyLoginEmails, TooManySignUps,
    UsernameAlreadyTaken,
)
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.participant import Participant
from liberapay.security.crypto import constant_time_compare
from liberapay.utils import get_ip_net
from liberapay.utils.emails import (
    EmailVerificationResult, check_email_blacklist, normalize_email_address,
)


class _ANON(object):
    ANON = True
    is_admin = False
    session = None
    id = None
    __bool__ = __nonzero__ = lambda *a: False
    get_tip_to = staticmethod(Participant._zero_tip)
    __repr__ = lambda self: '<ANON>'

    def get_currencies_for(self, tippee, tip):
        if isinstance(tippee, AccountElsewhere):
            tippee = tippee.participant
        return tip.amount.currency, tippee.accepted_currencies_set


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
        id = body['log-in.id'].strip()
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
                email_row = p.get_email(email)
                p.send_email('login_link', email_row, link_validity=SESSION_TIMEOUT)
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
        username = body.pop('sign-in.username', None)
        if username:
            username = username.strip()
            Participant.check_username(username)
        session_token = body.pop('sign-in.token', '')
        if session_token:
            Participant.check_session_token(session_token)
        # Check for an existing account
        existing_account = website.db.one("""
            SELECT p
              FROM emails e
              JOIN participants p ON p.id = e.participant
             WHERE lower(e.address) = lower(%s)
               AND ( e.verified IS TRUE OR
                     e.added_time > (current_timestamp - interval '1 day') OR
                     p.email IS NULL )
          ORDER BY p.join_time DESC
             LIMIT 1
        """, (email,))
        if existing_account:
            session = website.db.one("""
                SELECT id, secret, mtime
                  FROM user_secrets
                 WHERE participant = %s
                   AND id = 1
                   AND mtime < (%s + interval '6 hours')
                   AND mtime > (current_timestamp - interval '6 hours')
            """, (existing_account.id, existing_account.join_time))
            if session and constant_time_compare(session_token, session.secret):
                p = existing_account
                p.authenticated = True
                p.sign_in(response.headers.cookie, session=session)
                return p
            else:
                raise EmailAlreadyTaken(email)
        username_taken = website.db.one("""
            SELECT count(*)
              FROM participants p
             WHERE p.username = %s
        """, (username,))
        if username_taken:
            raise UsernameAlreadyTaken(username)
        # Rate limit
        request = state['request']
        src_addr, src_country = request.source, request.country
        website.db.hit_rate_limit('sign-up.ip-addr', str(src_addr), TooManySignUps)
        website.db.hit_rate_limit('sign-up.ip-net', get_ip_net(src_addr), TooManySignUps)
        website.db.hit_rate_limit('sign-up.country', src_country, TooManySignUps)
        website.db.hit_rate_limit('sign-up.ip-version', src_addr.version, TooManySignUps)
        # Okay, create the account
        with website.db.get_cursor() as c:
            p = Participant.make_active(kind, currency, username, cursor=c)
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

    db = state['website'].db
    if not db:
        return

    # Try to authenticate the user
    # We want to try cookie auth first, but we want password and email auth to
    # supersede it.
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
    redirect = False
    redirect_url = None
    if request.method == 'POST':
        # Password auth
        body = _get_body(request)
        if body:
            p = sign_in_with_form_data(body, state)
            carry_on = body.pop('log-in.carry-on', None)
            if p:
                redirect = body.get('form.repost', None) != 'true'
                redirect_url = body.get('sign-in.back-to') or request.line.uri.decoded
            elif carry_on:
                p_email = session_p and session_p.get_email_address()
                if p_email != carry_on:
                    state['log-in.carry-on'] = carry_on
                    raise LoginRequired
    elif request.method == 'GET' and request.qs.get('log-in.id'):
        # Email auth
        id = request.qs.get('log-in.id')
        session_id = request.qs.get('log-in.key')
        token = request.qs.get('log-in.token')
        if not (token and token.endswith('.em')):
            raise response.render('simplates/bad-login-link.spt', state)
        p = Participant.authenticate(id, session_id, token)
        if p:
            redirect = True
            session_p = p
            session_suffix = '.em'
        else:
            raise response.render('simplates/bad-login-link.spt', state)
        del request.qs['log-in.id'], request.qs['log-in.key'], request.qs['log-in.token']

    # Handle email verification
    email_id = request.qs.get_int('email.id', default=None)
    email_nonce = request.qs.get('email.nonce', '')
    if email_id and not request.path.raw.endswith('/disavow'):
        email_participant, email_is_already_verified = db.one("""
            SELECT p, e.verified
              FROM emails e
              JOIN participants p On p.id = e.participant
             WHERE e.id = %s
        """, (email_id,), default=(None, None))
        if email_participant:
            result = email_participant.verify_email(email_id, email_nonce, p)
            state['email.verification-result'] = result
            if result == EmailVerificationResult.SUCCEEDED or email_is_already_verified:
                del request.qs['email.id'], request.qs['email.nonce']
        del email_participant

    # Set up the new session
    if p:
        if session_p:
            session_p.sign_out(response.headers.cookie)
        if p.status == 'closed':
            p.update_status('active')
        if not p.session:
            p.sign_in(response.headers.cookie, suffix=session_suffix)
        state['user'] = p

    # Redirect if appropriate
    if redirect:
        if not redirect_url:
            # Build the redirect URL with the querystring as it is now (we've
            # probably removed items from it at this point).
            redirect_url = request.path.raw + request.qs.serialize()
        response.redirect(redirect_url, trusted_url=False)


def add_auth_to_response(response, request=None, user=ANON):
    if request is None:
        return  # early parsing must've failed
    if request.line.uri.startswith(b'/assets/'):
        return  # assets never get auth headers

    if SESSION in request.headers.cookie:
        if user.session:
            user.keep_signed_in(response.headers.cookie)
