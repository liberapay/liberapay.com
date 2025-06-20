"""Defines website authentication helpers.
"""

from hashlib import blake2b
from time import sleep

from pando import Response
from pando.utils import utcnow

from liberapay.constants import (
    ASCII_ALLOWED_IN_USERNAME, SESSION, SESSION_REFRESH, SESSION_TIMEOUT,
)
from liberapay.exceptions import (
    AccountIsPasswordless, EmailAlreadyTaken, LoginRequired,
    TooManyLogInAttempts, TooManyLoginEmails, TooManySignUps,
    UsernameAlreadyTaken,
)
from liberapay.models.participant import Participant
from liberapay.security.crypto import constant_time_compare
from liberapay.security.csrf import require_cookie
from liberapay.utils import b64encode_s, get_ip_net, get_recordable_headers
from liberapay.utils.emails import (
    EmailVerificationResult, normalize_and_check_email_address,
    normalize_email_address, remove_email_address_from_blacklist,
)


class _ANON:
    ANON = True
    id = None
    session = None
    session_type = None

    __bool__ = lambda *a: False
    __repr__ = lambda self: '<ANON>'

    get_currencies_for = staticmethod(Participant.get_currencies_for)
    get_tip_to = staticmethod(Participant._zero_tip)
    guessed_country = Participant._guessed_country

    def is_acting_as(self, privilege):
        return False

    def require_active_privilege(self, privilege):
        raise LoginRequired()

    def require_write_permission(self):
        raise LoginRequired()


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
        src_addr, src_country = request.source, request.source_country
        input_id = body['log-in.id'].strip()
        password = body.pop('log-in.password', None)
        id_type = None
        if input_id.find('@') > 0:
            id_type = 'email'
        elif input_id.startswith('~'):
            id_type = 'immutable'
        elif set(input_id).issubset(ASCII_ALLOWED_IN_USERNAME):
            id_type = 'username'
        if password and id_type:
            website.db.hit_rate_limit('log-in.password.ip-addr', str(src_addr), TooManyLogInAttempts)
            if id_type == 'immutable':
                p_id = Participant.check_id(input_id[1:])
            else:
                p_id = Participant.get_id_for(id_type, input_id)
            if p_id:
                try:
                    p = Participant.authenticate_with_password(p_id, password)
                except AccountIsPasswordless:
                    if id_type == 'email':
                        state['log-in.email'] = input_id
                    else:
                        state['log-in.error'] = _(
                            "Your account doesn't have a password, so you'll "
                            "have to authenticate yourself via email:"
                        )
                    return
            else:
                p = None
            if p:
                website.db.decrement_rate_limit('log-in.password.ip-addr', str(src_addr))
            else:
                state['log-in.error'] = (
                    _("The submitted password is incorrect.") if p_id is not None else
                    _("“{0}” is not a valid account ID.", input_id) if id_type == 'immutable' else
                    _("No account has the username “{username}”.", username=input_id) if id_type == 'username' else
                    _("No account has “{email_address}” as its primary email address.", email_address=input_id)
                )
        elif id_type == 'email':
            website.db.hit_rate_limit('log-in.email.ip-addr', str(src_addr), TooManyLogInAttempts)
            website.db.hit_rate_limit('log-in.email.ip-net', get_ip_net(src_addr), TooManyLogInAttempts)
            website.db.hit_rate_limit('log-in.email.country', src_country, TooManyLogInAttempts)
            normalized_email = normalize_email_address(input_id.lower())
            p = Participant.from_email(normalized_email)
            if p and p.kind == 'group':
                state['log-in.error'] = _(
                    "{0} is linked to a team account. It's not possible to log in as a team.",
                    input_id
                )
            elif p:
                email_row = p.get_email(normalized_email)
                if not email_row.verified:
                    website.db.hit_rate_limit('log-in.email.not-verified', normalized_email, TooManyLoginEmails)
                website.db.hit_rate_limit('log-in.email', p.id, TooManyLoginEmails)
                p.send_email('login_link', email_row, link_validity=SESSION_TIMEOUT)
                state['log-in.email-sent-to'] = input_id
                raise LoginRequired
            else:
                state['log-in.error'] = _(
                    "No account has “{email_address}” as its primary email address.",
                    email_address=input_id
                )
            p = None
        else:
            state['log-in.error'] = _("\"{0}\" is not a valid email address.", input_id)
            return

    elif 'sign-in.email' in body:
        response = state['response']
        # Check the submitted data
        kind = body.pop('sign-in.kind', 'individual')
        if kind not in ('individual', 'organization'):
            raise response.invalid_input(kind, 'sign-in.kind', 'body')
        email = body['sign-in.email']
        if not email:
            raise response.error(400, 'email is required')
        email = normalize_and_check_email_address(email)
        currency = (
            body.get_currency('sign-in.currency', None, phased_out='replace') or
            body.get_currency('currency', None, phased_out='replace') or
            state.get('currency') or
            'EUR'
        )
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
            if session and constant_time_compare(session_token, session.secret.split('.')[0]):
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
        src_addr, src_country = request.source, request.source_country
        website.db.hit_rate_limit('sign-up.ip-addr', str(src_addr), TooManySignUps)
        website.db.hit_rate_limit('sign-up.ip-net', get_ip_net(src_addr), TooManySignUps)
        website.db.hit_rate_limit('sign-up.country', src_country, TooManySignUps)
        website.db.hit_rate_limit('sign-up.ip-version', src_addr.version, TooManySignUps)
        # Okay, create the account
        with website.db.get_cursor() as c:
            request_data = {
                'url': request.line.uri.decoded,
                'headers': get_recordable_headers(request),
            }
            p = Participant.make_active(kind, currency, username, cursor=c, request_data=request_data)
            p.set_email_lang(state['locale'].tag, cursor=c)
            p.add_email(email, cursor=c)
        p.authenticated = True
        p.sign_in(response.headers.cookie, token=session_token, suffix='.in')
        website.logger.info(f"a new participant has joined: ~{p.id}")
        # We're done, we can clean up the body now
        body.pop('sign-in.email')
        body.pop('sign-in.currency', None)
        body.pop('sign-in.username', None)
        body.pop('sign-in.token', None)

    return p


def start_user_as_anon():
    """Make sure we always have a user object, regardless of exceptions during authentication.
    """
    return {'user': ANON}


def authenticate_user_if_possible(csrf_token, request, response, state, user, _):
    """This signs the user in.
    """
    if state.get('etag') or request.path.raw.startswith('/callbacks/'):
        return

    db = state['website'].db
    if not db:
        return

    # Try to authenticate the user
    # We want to try cookie auth first, but we want password and email auth to
    # supersede it.
    session_p = None
    if SESSION in request.cookies:
        creds = request.cookies[SESSION].split(':', 2)
        if len(creds) == 2:
            creds = [creds[0], 1, creds[1]]
        if len(creds) == 3:
            session_p, state['session_status'] = Participant.authenticate_with_session(
                *creds, allow_downgrade=True, cookies=response.headers.cookie
            )
            if session_p:
                user = state['user'] = session_p
    p = None
    session_suffix = ''
    redirect = False
    redirect_url = None
    if request.method == 'POST':
        # Form auth
        body = _get_body(request)
        if body:
            redirect = body.get('form.repost', None) != 'true'
            redirect_url = body.get('sign-in.back-to')
            # Remove email address from blacklist if requested
            email_address = body.pop('email.unblacklist', None)
            if email_address:
                remove_email_address_from_blacklist(email_address, user, request)
            # Proceed with form auth
            carry_on = body.pop('log-in.carry-on', None)
            if carry_on:
                can_carry_on = (
                    session_p is not None and
                    session_p.session_type != 'ro' and
                    session_p.get_email_address() == carry_on
                )
                if not can_carry_on:
                    state['log-in.carry-on'] = carry_on
                    raise LoginRequired
            else:
                p = sign_in_with_form_data(body, state)
                if p:
                    if not p.session:
                        session_suffix = '.pw'  # stands for "password"
                else:
                    redirect = False
    elif request.method == 'GET':
        if request.qs.get('log-in.id') or request.qs.get('email.id'):
            # Prevent email software from messing up an email log-in or confirmation
            # with a single GET request. Also, show a proper warning to someone trying
            # to log in while cookies are disabled.
            require_cookie(state)

        if request.qs.get('log-in.id'):
            # Email auth
            id = request.qs.get_int('log-in.id')
            session_id = request.qs.get('log-in.key')
            if not session_id or session_id < '1001' or session_id > '1010':
                raise response.render('simplates/log-in-link-is-invalid.spt', state)
            token = request.qs.get('log-in.token')
            required = request.qs.parse_boolean('log-in.required', default=True)
            p = Participant.authenticate_with_session(
                id, session_id, token,
                allow_downgrade=not required, cookies=response.headers.cookie,
            )[0]
            if p:
                if p.id != user.id:
                    response.headers[b'Referrer-Policy'] = b'strict-origin'
                    submitted_confirmation_token = request.qs.get('log-in.confirmation')
                    if submitted_confirmation_token:
                        expected_confirmation_token = b64encode_s(blake2b(
                            token.encode('ascii'),
                            key=csrf_token.token.encode('ascii'),
                            digest_size=48,
                        ).digest())
                        confirmation_tokens_match = constant_time_compare(
                            expected_confirmation_token,
                            submitted_confirmation_token
                        )
                        if not confirmation_tokens_match:
                            raise response.invalid_input(
                                submitted_confirmation_token,
                                'log-in.confirmation',
                                'querystring'
                            )
                        del request.qs['log-in.confirmation']
                    else:
                        raise response.render('simplates/log-in-link-is-valid.spt', state)
                redirect = True
                db.run("""
                    DELETE FROM user_secrets
                     WHERE participant = %s
                       AND id = %s
                       AND mtime = %s
                """, (p.id, p.session.id, p.session.mtime))
                p.session = None
                session_suffix = token[-3:]
            elif required:
                raise response.render('simplates/log-in-link-is-invalid.spt', state)
            del request.qs['log-in.id'], request.qs['log-in.key'], request.qs['log-in.token']
            request.qs.pop('log-in.required', None)

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
                result = email_participant.verify_email(email_id, email_nonce, p or user, request)
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
        if p.status == 'closed':
            p.update_status('active')
        if p.is_suspended:
            session_suffix = '.ro'
        if session_p:
            p.regenerate_session(
                session_p.session, response.headers.cookie, suffix=session_suffix
            )
        if not p.session:
            p.sign_in(response.headers.cookie, suffix=session_suffix)
        user = state['user'] = p

    # Downgrade the session to read-only if the account is suspended
    if user and user.is_suspended and not user.session.secret.endswith('.ro'):
        user.regenerate_session(user.session, response.headers.cookie, suffix='.ro')

    # Redirect if appropriate
    if redirect:
        if not redirect_url:
            # Build the redirect URL with the querystring as it is now (we've
            # probably removed items from it at this point).
            redirect_url = request.path.raw + request.qs.serialize()
        response.redirect(redirect_url, trusted_url=False)


def refresh_user_session(response, user=ANON, etag=None):
    if etag:
        return  # cachable responses should never contain cookies
    if user.session and user.session.mtime < (utcnow() - SESSION_REFRESH):
        user.regenerate_session(user.session, response.headers.cookie)
