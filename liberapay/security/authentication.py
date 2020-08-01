"""Defines website authentication helpers.
"""

from time import sleep

from pando import Response

from liberapay.constants import (
    CURRENCIES, PASSWORD_MIN_SIZE, PASSWORD_MAX_SIZE, SESSION, SESSION_TIMEOUT
)
from liberapay.exceptions import (
    BadPasswordSize, EmailAlreadyTaken, LoginRequired,
    TooManyLogInAttempts, TooManyLoginEmails, TooManyRequests, TooManySignUps,
    UsernameAlreadyTaken,
)
from liberapay.models.participant import Participant
from liberapay.security.crypto import constant_time_compare
from liberapay.utils import b64encode_s, get_ip_net
from liberapay.utils.emails import (
    EmailVerificationResult, normalize_and_check_email_address,
    remove_email_address_from_blacklist,
)


class _ANON(object):
    ANON = True
    is_admin = False
    session = None
    id = None

    __bool__ = __nonzero__ = lambda *a: False
    __repr__ = lambda self: '<ANON>'

    get_currencies_for = staticmethod(Participant.get_currencies_for)
    get_tip_to = staticmethod(Participant._zero_tip)


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
        id = body['log-in.id'].strip()
        password = body.pop('log-in.password', None)
        k = 'email' if '@' in id else 'username'
        if password:
            website.db.hit_rate_limit('log-in.password.ip-addr', str(src_addr), TooManyLogInAttempts)
            website.db.hit_rate_limit('hash_password.ip-addr', str(src_addr), TooManyRequests)
            p_id = Participant.get_id_for(k, id)
            p = Participant.authenticate(p_id, 0, password)
            if not p:
                state['log-in.error'] = (
                    _("The submitted password is incorrect.") if p_id is not None else
                    _("No account has the username “{username}”.", username=id) if k == 'username' else
                    _("No account has “{email_address}” as its primary email address.", email_address=id)
                )
            else:
                website.db.decrement_rate_limit('log-in.password.ip-addr', str(src_addr))
                try:
                    p.check_password(password, context='login')
                except Exception as e:
                    website.tell_sentry(e, state)
        elif k == 'username':
            state['log-in.error'] = _("\"{0}\" is not a valid email address.", id)
            return
        else:
            website.db.hit_rate_limit('log-in.email.ip-addr', str(src_addr), TooManyLogInAttempts)
            website.db.hit_rate_limit('log-in.email.ip-net', get_ip_net(src_addr), TooManyLogInAttempts)
            website.db.hit_rate_limit('log-in.email.country', src_country, TooManyLogInAttempts)
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
                    "No account has “{email_address}” as its primary email address.",
                    email_address=id
                )
            p = None

    elif 'sign-in.email' in body:
        response = state['response']
        # Check the submitted data
        kind = body.pop('sign-in.kind', 'individual')
        if kind not in ('individual', 'organization'):
            raise response.invalid_input(kind, 'sign-in.kind', 'body')
        email = body['sign-in.email']
        if not email:
            raise response.error(400, 'email is required')
        email = normalize_and_check_email_address(email, state)
        currency = body.get('sign-in.currency', 'EUR')
        if currency not in CURRENCIES:
            raise response.invalid_input(currency, 'sign-in.currency', 'body')
        password = body.get('sign-in.password')
        if password:
            l = len(password)
            if l < PASSWORD_MIN_SIZE or l > PASSWORD_MAX_SIZE:
                raise BadPasswordSize
        username = body.get('sign-in.username')
        if username:
            username = username.strip()
            Participant.check_username(username)
        session_token = body.get('sign-in.token', '')
        if session_token:
            Participant.check_session_token(session_token)
        # Check for an existing account
        is_duplicate_request = website.db.hit_rate_limit('sign-up.email', email) is None
        for i in range(5):
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
            if is_duplicate_request and not existing_account:
                # The other thread hasn't created the account yet.
                sleep(1)
            else:
                break
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
            decode = lambda b: b.decode('ascii', 'backslashreplace')
            request_data = {
                'url': request.line.uri.decoded,
                'headers': {
                    decode(k): decode(b', '.join(v))
                    for k, v in request.headers.items()
                    if k != b'Cookie'
                },
            }
            p = Participant.make_active(kind, currency, username, cursor=c, request_data=request_data)
            p.set_email_lang(state['locale'].language, cursor=c)
            p.add_email(email, cursor=c)
        if password:
            p.update_password(password)
            p.check_password(password, context='login')
        p.authenticated = True
        p.sign_in(response.headers.cookie, token=session_token)
        # We're done, we can clean up the body now
        body.pop('sign-in.email')
        body.pop('sign-in.currency', None)
        body.pop('sign-in.password', None)
        body.pop('sign-in.username', None)
        body.pop('sign-in.token', None)

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
        # Form auth
        body = _get_body(request)
        if body:
            # Remove email address from blacklist if requested
            email_address = body.pop('email.unblacklist', None)
            if email_address:
                remove_email_address_from_blacklist(email_address, user, request)
            # Proceed with form auth
            carry_on = body.pop('log-in.carry-on', None)
            if carry_on:
                p_email = session_p and session_p.get_email_address()
                if p_email != carry_on:
                    state['log-in.carry-on'] = carry_on
                    raise LoginRequired
            else:
                p = sign_in_with_form_data(body, state)
                if p:
                    redirect = body.get('form.repost', None) != 'true'
                    redirect_url = body.get('sign-in.back-to') or request.line.uri.decoded
    elif request.method == 'GET':
        if request.qs.get('log-in.id'):
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
                request.qs.pop('email.id', None)
                request.qs.pop('email.nonce', None)
                if result == EmailVerificationResult.SUCCEEDED:
                    request.qs.add('success', b64encode_s(
                        _("Your email address is now verified.")
                    ))
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


def add_auth_to_response(response, request=None, user=ANON, etag=None):
    if request is None:
        return  # early parsing must've failed
    if etag:
        return  # cachable responses should never contain cookies

    if SESSION in request.headers.cookie:
        if user.session:
            user.keep_signed_in(response.headers.cookie)
