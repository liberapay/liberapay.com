from base64 import b64decode, b64encode
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from email.utils import formataddr
from functools import cached_property
from hashlib import pbkdf2_hmac, md5, sha1
from operator import attrgetter, itemgetter
from os import urandom
from random import randint
from threading import Lock
from time import sleep
from types import SimpleNamespace
import unicodedata
from urllib.parse import quote as urlquote, urlencode
import uuid

import aspen_jinja2_renderer
from dateutil.parser import parse as parse_date
from dns.exception import DNSException
from dns.resolver import Cache as DNSCache, Resolver as DNSResolver
from html2text import html2text
from markupsafe import escape as htmlescape
from pando import json, Response
from pando.utils import utcnow
from postgres.orm import Model
from psycopg2.errors import IntegrityError, ReadOnlySqlTransaction
from psycopg2.extras import execute_batch, execute_values
import requests
import stripe

from liberapay.billing.payday import compute_next_payday_date
from liberapay.constants import (
    ASCII_ALLOWED_IN_USERNAME, BASE64URL_CHARS, CURRENCIES,
    DONATION_LIMITS, EMAIL_VERIFICATION_TIMEOUT, EVENTS, HTML_A,
    PASSWORD_MAX_SIZE, PASSWORD_MIN_SIZE, PAYPAL_CURRENCIES,
    PERIOD_CONVERSION_RATES, PRIVILEGES,
    PUBLIC_NAME_MAX_SIZE, SEPA, SESSION, SESSION_TIMEOUT, SESSION_TIMEOUT_LONG,
    USERNAME_MAX_SIZE, USERNAME_SUFFIX_BLACKLIST,
)
from liberapay.exceptions import (
    AccountIsPasswordless,
    AccountSuspended,
    BadAmount,
    BadDonationCurrency,
    BadPasswordSize,
    CannotRemovePrimaryEmail,
    DuplicateNotification,
    EmailAddressIsBlacklisted,
    EmailAlreadyTaken,
    EmailNotVerified,
    InvalidId,
    LoginRequired,
    NonexistingElsewhere,
    NoSelfTipping,
    NoTippee,
    TooManyAttempts,
    TooManyCurrencyChanges,
    TooManyEmailAddresses,
    TooManyEmailVerifications,
    TooManyLogInAttempts,
    TooManyPasswordLogins,
    TooManyRequests,
    TooManyTeamsCreated,
    TooManyUsernameChanges,
    UnableToSendEmail,
    UnacceptedDonationVisibility,
    UnexpectedCurrency,
    UsernameAlreadyTaken,
    UsernameBeginsWithRestrictedCharacter,
    UsernameContainsInvalidCharacters,
    UsernameEndsWithForbiddenSuffix,
    UsernameIsEmpty,
    UsernameIsPurelyNumerical,
    UsernameIsRestricted,
    UsernameTooLong,
    ValueTooLong,
    ValueContainsForbiddenCharacters,
    VerificationEmailAlreadySent,
)
from liberapay.i18n import base as i18n
from liberapay.i18n.currencies import Money
from liberapay.models._mixin_team import MixinTeam
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.community import Community
from liberapay.models.tip import Tip
from liberapay.payin.common import resolve_amounts
from liberapay.payin.prospect import PayinProspect
from liberapay.security.crypto import constant_time_compare
from liberapay.utils import (
    deserialize, erase_cookie, get_recordable_headers, serialize, set_cookie,
    tweak_avatar_url,
    markdown,
)
from liberapay.utils.emails import (
    NormalizedEmailAddress, EmailVerificationResult, check_email_blacklist,
    normalize_email_address,
)
from liberapay.utils.types import LocalizedString, Object
from liberapay.website import website


FOUR_WEEKS = timedelta(weeks=4)
TEN_YEARS = timedelta(days=3652)


email_lock = Lock()

DNS = DNSResolver()
DNS.lifetime = 1.0  # 1 second timeout, per https://github.com/liberapay/liberapay.com/pull/1043#issuecomment-377891723
DNS.cache = DNSCache()


class Participant(Model, MixinTeam):

    typname = 'participants'

    ANON = False
    EMAIL_VERIFICATION_TIMEOUT = EMAIL_VERIFICATION_TIMEOUT

    session = None

    def __eq__(self, other):
        if not isinstance(other, Participant):
            return False
        return self.id == other.id

    def __ne__(self, other):
        if not isinstance(other, Participant):
            return True
        return self.id != other.id

    def __repr__(self):
        return '<Participant #%r %r>' % (self.id, self.username)


    # Constructors
    # ============

    @classmethod
    def make_stub(cls, cursor=None, **kw):
        """Return a new stub participant.
        """
        if kw:
            cols, vals = zip(*kw.items())
            cols = ', '.join(cols)
            placeholders = ', '.join(['%s']*len(vals))
            x = '({0}) VALUES ({1})'.format(cols, placeholders)
        else:
            x, vals = 'DEFAULT VALUES', ()
        with cls.db.get_cursor(cursor) as c:
            return c.one("""
                INSERT INTO participants {0}
                  RETURNING participants.*::participants
            """.format(x), vals)

    @classmethod
    def make_active(cls, kind, currency, username=None, cursor=None, request_data=None):
        """Return a new active participant.
        """
        now = utcnow()
        d = {
            'kind': kind,
            'status': 'active',
            'join_time': now,
            'main_currency': currency,
            'accepted_currencies': currency,
        }
        cols, vals = zip(*d.items())
        cols = ', '.join(cols)
        placeholders = ', '.join(['%s']*len(vals))
        with cls.db.get_cursor(cursor) as c:
            p = c.one("""
                INSERT INTO participants ({0}) VALUES ({1})
                  RETURNING participants.*::participants
            """.format(cols, placeholders), vals)
            p.add_event(c, 'sign_up_request', request_data)
            if username:
                p.change_username(username, cursor=c)
        return p

    def make_team(self, name, currency, email=None, email_lang=None, throttle_takes=True):
        if email and not isinstance(email, NormalizedEmailAddress):
            raise TypeError("expected NormalizedEmailAddress, got %r" % type(email))
        with self.db.get_cursor() as c:
            c.hit_rate_limit('make_team', self.id, TooManyTeamsCreated)
            t = c.one("""
                INSERT INTO participants
                            (kind, status, join_time, throttle_takes, main_currency)
                     VALUES ('group', 'active', now(), %s, %s)
                  RETURNING participants.*::participants
            """, (throttle_takes, currency))
            t.change_username(name, cursor=c)
            t.add_member(self, c)
            if email:
                t.set_email_lang(email_lang, cursor=c)
                t.add_email(email, cursor=c)
        return t

    def leave_team(self, team):
        team.set_take_for(self, None, self)

    @classmethod
    def from_id(cls, id, _raise=True):
        """Return an existing participant based on id.
        """
        r = cls.db.one("SELECT p FROM participants p WHERE id = %s", (id,))
        if r is None and _raise:
            raise InvalidId(id, cls.__name__)
        return r

    @classmethod
    def from_username(cls, username, id_only=False):
        """Return an existing participant based on username.
        """
        return cls.db.one("""
            SELECT {0} FROM participants p WHERE lower(username) = %s
        """.format('p.id' if id_only else 'p'), (username.lower(),))

    @classmethod
    def from_email(cls, email, id_only=False):
        # This query looks for an unverified address if the participant
        # doesn't have any verified address
        return cls.db.one("""
            SELECT {0}
              FROM emails e
              JOIN participants p ON p.id = e.participant
             WHERE lower(e.address) = %s
               AND (p.email IS NOT NULL AND lower(p.email) = lower(e.address)
                    OR
                    p.email IS NULL AND e.id = (
                        SELECT e2.id
                          FROM emails e2
                         WHERE e2.participant = e.participant
                      ORDER BY e2.disavowed IS NOT true DESC
                             , ( SELECT count(b)
                                   FROM email_blacklist b
                                  WHERE lower(b.address) = lower(e2.address)
                                    AND (b.ignore_after IS NULL OR
                                         b.ignore_after > current_timestamp)
                               ) ASC
                             , e2.added_time ASC
                         LIMIT 1
                    )
                   )
          ORDER BY p.email IS NOT NULL DESC, p.status = 'active' DESC, p.id ASC
             LIMIT 1
        """.format('p.id' if id_only else 'p'), (email.lower(),))

    @classmethod
    def check_id(cls, p_id):
        try:
            p_id = int(p_id)
        except (ValueError, TypeError):
            return
        return cls.db.one("SELECT id FROM participants WHERE id = %s", (p_id,))

    @classmethod
    def get_id_for(cls, type_of_id, id_value):
        return getattr(cls, 'from_' + type_of_id)(id_value, id_only=True)

    def refetch(self):
        r = self.db.one("SELECT p FROM participants p WHERE id = %s", (self.id,))
        r.session = self.session
        return r


    # Password Management
    # ===================

    @classmethod
    def authenticate_with_password(cls, p_id, password, context='log-in'):
        """Fetch a participant using its ID, but only if the provided password is valid.

        Args:
            p_id (int): the participant's ID
            password (str): the participant's password
            context (str): the operation that this authentication is part of

        Return type: `Participant | None`

        Raises:
            AccountIsPasswordless if the account doesn't have a password
        """
        r = cls.db.one("""
            SELECT p, s.secret, s.mtime
              FROM user_secrets s
              JOIN participants p ON p.id = s.participant
             WHERE s.participant = %s
               AND s.id = 0
        """, (p_id,))
        if not r:
            raise AccountIsPasswordless()
        if not password:
            return None
        p, stored_secret, mtime = r
        if context == 'log-in':
            cls.db.hit_rate_limit('log-in.password', p.id, TooManyPasswordLogins)
        request = website.state.get({}).get('request')
        if request:
            cls.db.hit_rate_limit('hash_password.ip-addr', str(request.source), TooManyRequests)
        algo, rounds, salt, hashed = stored_secret.split('$', 3)
        rounds = int(rounds)
        salt, hashed = b64decode(salt), b64decode(hashed)
        if constant_time_compare(cls._hash_password(password, algo, salt, rounds), hashed):
            if context == 'log-in':
                password_status = None
                last_password_check = p.get_last_event_of_type('password-check')
                if last_password_check and utcnow() - last_password_check.ts < timedelta(days=180):
                    last_password_warning = cls.db.one("""
                        SELECT n.*
                          FROM notifications n
                         WHERE n.participant = %s
                           AND n.event = 'password_warning'
                           AND n.ts > %s
                      ORDER BY n.ts DESC
                         LIMIT 1
                    """, (p.id, mtime))
                    if last_password_warning:
                        password_status = deserialize(last_password_warning.context)[
                            'password_status'
                        ]
                else:
                    try:
                        password_status = p.check_password(password)
                    except Exception as e:
                        website.tell_sentry(e)
                    else:
                        if password_status != 'okay':
                            p.notify(
                                'password_warning',
                                email=False,
                                type='warning',
                                password_status=password_status,
                            )
                        p.add_event(website.db, 'password-check', None)
                if password_status and password_status != 'okay':
                    raise AccountIsPasswordless()
                cls.db.decrement_rate_limit('log-in.password', p.id)
            p.authenticated = True
            if len(salt) < 32:
                # Update the password hash in the DB
                hashed = cls.hash_password(password)
                cls.db.run(
                    "UPDATE user_secrets SET secret = %s WHERE participant = %s AND id = 0",
                    (hashed, p.id)
                )
            return p

    @staticmethod
    def _hash_password(password, algo, salt, rounds):
        return pbkdf2_hmac(algo, password.encode('utf8'), salt, rounds)

    @classmethod
    def hash_password(cls, password):
        # Using SHA-256 as the HMAC algorithm (PBKDF2 + HMAC-SHA-256)
        algo = 'sha256'
        # Generate 32 random bytes for the salt
        salt = urandom(32)
        rounds = website.app_conf.password_rounds
        hashed = cls._hash_password(password, algo, salt, rounds)
        hashed = '$'.join((
            algo,
            str(rounds),
            b64encode(salt).decode('ascii'),
            b64encode(hashed).decode('ascii')
        ))
        return hashed

    def update_password(self, password_field_name):
        state = website.state.get()
        request, response = state['request'], state['response']
        password = request.body[password_field_name]
        l = len(password)
        if l < PASSWORD_MIN_SIZE or l > PASSWORD_MAX_SIZE:
            raise BadPasswordSize
        website.db.hit_rate_limit('change_password', self.id, TooManyAttempts)
        password_status = None
        skip_check = state['environ'].get(b'skip_password_check')
        if not skip_check:
            try:
                password_status = self.check_password(password)
            except Exception as e:
                website.tell_sentry(e)
            if password_status and password_status != 'okay':
                raise response.render(
                    'simplates/password-warning.spt', state,
                    password_field_name=password_field_name,
                    password_status=password_status,
                )
        hashed = self.hash_password(password)
        p_id = self.id
        current_session_id = getattr(self.session, 'id', 0)
        with self.db.get_cursor() as c:
            c.run("""
                INSERT INTO user_secrets
                            (participant, id, secret)
                     VALUES (%(p_id)s, 0, %(hashed)s)
                ON CONFLICT (participant, id) DO UPDATE
                        SET secret = excluded.secret
                          , mtime = current_timestamp;

                DELETE FROM user_secrets
                 WHERE participant = %(p_id)s
                   AND id >= 1 AND id <= 20
                   AND id <> %(current_session_id)s
                   AND secret NOT LIKE '%%.em';
            """, locals())
            if password_status:
                self.add_event(c, 'password-check', None)

    def unset_password(self):
        params = dict(
            p_id=self.id,
            current_session_id=getattr(self.session, 'id', -1),
        )
        with self.db.get_cursor() as c:
            r = c.one("""
                DELETE FROM user_secrets
                 WHERE participant = %(p_id)s
                   AND id = 0
             RETURNING 1
            """, params)
            if not r:
                return
            self.add_event(c, 'unset_password', None)
            # Invalidate other password sessions
            c.run("""
                DELETE FROM user_secrets
                 WHERE participant = %(p_id)s
                   AND id >= 1 AND id <= 20
                   AND id <> %(current_session_id)s
                   AND secret NOT LIKE '%%.em'
            """, params)

    @cached_property
    def has_password(self):
        return self.db.one("""
            SELECT participant
              FROM user_secrets
             WHERE participant = %s
               AND id = 0
               AND NOT EXISTS (
                       SELECT 1
                         FROM notifications n
                        WHERE n.participant = user_secrets.participant
                          AND n.event = 'password_warning'
                          AND n.ts > user_secrets.mtime
                        LIMIT 1
                   )
        """, (self.id,)) is not None

    def check_password(self, password):
        passhash = sha1(password.encode("utf-8")).hexdigest().upper()
        passhash_prefix, passhash_suffix = passhash[:5], passhash[5:]
        url = "https://api.pwnedpasswords.com/range/" + passhash_prefix
        r = requests.get(url=url)
        count = 0
        for line in r.text.split():
            parts = line.split(":")
            if parts[0] == passhash_suffix:
                count = int(parts[1])
        if count > 500:
            status = 'common'
        elif count > 0:
            status = 'compromised'
        else:
            status = 'okay'
        return status


    # Session Management
    # ==================

    @classmethod
    def authenticate_with_session(
        cls, p_id, session_id, secret, allow_downgrade=False, cookies=None,
    ):
        """Fetch a participant using its ID, but only if the provided session is valid.

        Args:
            p_id (int | str): the participant's ID
            session_id (int | str): the ID of the session
            secret (str): the actual secret
            allow_downgrade (bool): allow downgrading to a read-only session
            cookies (SimpleCookie):
                the response cookies, only needed when `allow_downgrade` is `True`

        Return type:
            Tuple[Participant, Literal['valid']] |
            Tuple[None, Literal['expired', 'invalid']]
        """
        if not secret:
            if session_id == '!':
                return None, 'expired'
            return None, 'invalid'
        try:
            p_id = int(p_id)
            session_id = int(session_id)
        except (ValueError, TypeError):
            return None, 'invalid'
        if session_id < 1:
            return None, 'invalid'
        rate_limit = session_id >= 1001 and session_id <= 1010
        if rate_limit:
            request = website.state.get({}).get('request')
            if request:
                cls.db.hit_rate_limit(
                    'log-in.session.ip-addr', str(request.source), TooManyLogInAttempts
                )
            else:
                rate_limit = False
        r = cls.db.one("""
            SELECT p, s.secret, s.mtime, s.latest_use
              FROM user_secrets s
              JOIN participants p ON p.id = s.participant
             WHERE s.participant = %s
               AND s.id = %s
        """, (p_id, session_id))
        if not r:
            erase_cookie(cookies, SESSION)
            return None, 'invalid'
        p, stored_secret, mtime, latest_use = r
        if not constant_time_compare(stored_secret, secret):
            erase_cookie(cookies, SESSION)
            return None, 'invalid'
        if rate_limit:
            cls.db.decrement_rate_limit('log-in.session.ip-addr', str(request.source))
        now = utcnow()
        today = now.date()
        if session_id >= 800 and session_id < 810:
            if (latest_use or mtime.date()) < today - SESSION_TIMEOUT_LONG:
                return None, 'expired'
        elif mtime > now - SESSION_TIMEOUT:
            p.session = SimpleNamespace(id=session_id, secret=secret, mtime=mtime)
        elif allow_downgrade:
            if mtime > now - FOUR_WEEKS:
                p.regenerate_session(
                    SimpleNamespace(id=session_id, secret=secret, mtime=mtime),
                    cookies,
                    suffix='.ro',  # stands for "read only"
                )
            else:
                set_cookie(cookies, SESSION, f"{p.id}:!:", expires=now + TEN_YEARS)
                return None, 'expired'
        else:
            return None, 'expired'
        if not latest_use or latest_use < today:
            cls.db.run("""
                UPDATE user_secrets
                   SET latest_use = current_date
                 WHERE participant = %s
                   AND id = %s
            """, (p_id, session_id))
        p.authenticated = True
        return p, 'valid'

    @staticmethod
    def generate_session_token():
        return b64encode(urandom(24), b'-_').decode('ascii')

    @staticmethod
    def check_session_token(token):
        if len(token) < 32:
            raise Response(400, "bad token, too short")
        if not set(token).issubset(BASE64URL_CHARS):
            raise Response(400, "bad token, not base64url")

    def regenerate_session(self, session, cookies, suffix=None):
        """Replace a session's secret and timestamp with new ones.

        The new secret is guaranteed to be different from the old one.
        """
        if session.id >= 800 and session.id < 810:
            # Sessions in this range aren't meant to be regenerated automatically.
            return
        if self.is_suspended:
            if not suffix:
                suffix = '.ro'
            elif suffix != '.ro':
                raise AccountSuspended()
        self.session = self.db.one(r"""
            UPDATE user_secrets
               SET mtime = current_timestamp
                 , secret = %(new_secret)s || coalesce(
                       %(suffix)s,
                       regexp_replace(secret, '.+(\.[a-z]{2})$', '\1')
                   )
             WHERE participant = %(p_id)s
               AND id = %(session_id)s
               AND mtime = %(current_mtime)s
         RETURNING id, secret, mtime
        """, dict(
            new_secret=self.generate_session_token(),
            suffix=suffix,
            p_id=self.id,
            session_id=session.id,
            current_mtime=session.mtime,
        ))
        if self.session:
            if self.session.secret == session.secret:
                # Very unlikely, unless there's a bug in the generator. Try again.
                website.logger.info(
                    "The random generator returned the same token. This is only "
                    "indicative of a problem if it happens often."
                )
                return self.regenerate_session(session, cookies, suffix)
            creds = '%i:%i:%s' % (self.id, self.session.id, self.session.secret)
            set_cookie(cookies, SESSION, creds, expires=self.session.mtime + TEN_YEARS)

    def start_session(self, suffix='', token=None, id_min=1, id_max=20,
                      lifetime=FOUR_WEEKS):
        """Start a new session for the user.

        Args:
            suffix (str):
                the session type, preceded by a dot:
                    '.em' for email sessions
                    '.in' for initial sessions
                    '.pw' for password sessions
                    '.ro' for read-only sessions
            token (str):
                the session token, if it's already been generated
            id_min (int):
                the lowest acceptable session ID
            id_max (int):
                the highest acceptable session ID
            lifetime (timedelta):
                the session timeout, used to determine if existing sessions have expired

        The session ID is selected in the following order:
        1. if the oldest existing session has expired, then its ID is reused;
        2. if there are unused session IDs, then the lowest one is claimed;
        3. the oldest session is overwritten, even though it hasn't expired yet.

        """
        assert id_min < id_max, (id_min, id_max)
        if self.is_suspended:
            if not suffix:
                suffix = '.ro'
            elif suffix != '.ro':
                raise AccountSuspended()
        if token:
            if not token.endswith(suffix):
                self.check_session_token(token)
                token += suffix
        else:
            token = self.generate_session_token() + suffix
        p_id = self.id
        session = self.db.one("""
            WITH oldest_secret AS (
                     SELECT *
                       FROM user_secrets
                      WHERE participant = %(p_id)s
                        AND id >= %(id_min)s
                        AND id <= %(id_max)s
                   ORDER BY mtime
                      LIMIT 1
                 )
               , unused_id AS (
                     SELECT i
                       FROM generate_series(%(id_min)s, %(id_max)s) i
                      WHERE NOT EXISTS (
                                SELECT 1
                                  FROM user_secrets s2
                                 WHERE s2.participant = %(p_id)s
                                   AND s2.id = i
                            )
                   ORDER BY i
                      LIMIT 1
                 )
            INSERT INTO user_secrets AS s
                        (participant, id, secret)
                 SELECT %(p_id)s
                      , coalesce(
                            ( SELECT s2.id
                                FROM oldest_secret s2
                               WHERE s2.mtime < (current_timestamp - %(lifetime)s)
                            ),
                            (SELECT i FROM unused_id),
                            (SELECT s2.id FROM oldest_secret s2)
                        )
                      , %(token)s
            ON CONFLICT (participant, id) DO UPDATE
                    SET mtime = excluded.mtime
                      , secret = excluded.secret
                  WHERE s.mtime = (SELECT s2.mtime FROM oldest_secret s2)
              RETURNING *
        """, locals())
        if session is None:
            return self.start_session(token=token, id_min=id_min, id_max=id_max)
        return session

    def sign_in(self, cookies, session=None, **session_kw):
        assert self.authenticated
        self.session = session or self.start_session(**session_kw)
        creds = '%i:%i:%s' % (self.id, self.session.id, self.session.secret)
        set_cookie(cookies, SESSION, creds, self.session.mtime + TEN_YEARS)

    def sign_out(self, cookies):
        """End the user's current session.
        """
        self.db.run("DELETE FROM user_secrets WHERE participant = %s AND id = %s",
                    (self.id, self.session.id))
        del self.session
        erase_cookie(cookies, SESSION)

    @property
    def session_type(self):
        session = self.session
        if session:
            if not hasattr(session, 'type'):
                i = session.secret.rfind('.')
                session.type = session.secret[i+1:] if i > 0 else ''
            return session.type

    def require_write_permission(self):
        session_type = self.session_type
        if session_type is None:
            # This isn't supposed to happen.
            try:
                raise AssertionError("session is None when it shouldn't be")
            except Exception as e:
                website.tell_sentry(e)
            self.require_reauthentication()
        elif session_type == 'ro':
            self.require_reauthentication()


    # Privileges
    # ==========

    def has_privilege(self, p):
        """Checks whether the participant has the specified privilege.

        A participant who has the 'admin' privilege is considered to have all
        other privileges.
        """
        return self.privileges & (PRIVILEGES[p] | 1)

    def is_acting_as(self, privilege):
        """Checks whether the participant can currently use the specified privilege.

        This method is more strict than `has_privilege`, it only returns `True`
        if the user is currently logged in and has a fresh session.

        If the user's session is read-only, then the user is asked to reauthenticate
        themself.
        """
        if self.has_privilege(privilege):
            session_type = self.session_type
            if session_type == 'ro':
                self.require_reauthentication()
            if session_type is not None:
                return True
        return False

    def require_active_privilege(self, privilege):
        """Like `is_acting_as`, but raises an exception instead of returning `False`.
        """
        if self.has_privilege(privilege):
            session_type = self.session_type
            if session_type == 'ro':
                self.require_reauthentication()
            if session_type is not None:
                return
        raise Response(403, f"You don't have the {privilege} privilege.")

    def require_reauthentication(self):
        if self.is_suspended:
            raise AccountSuspended()
        state = website.state.get()
        state['log-in.reauthenticate'] = True
        email = self.get_email_address()
        if self.has_password:
            state['log-in.password-or-email'] = email
        else:
            state['log-in.email'] = email
        raise LoginRequired()

    # Statement
    # =========

    def get_statement(self, langs, type='profile'):
        """Get the participant's statement in the language that best matches
        the list provided, or the participant's "primary" statement if there
        are no matches. Returns a `LocalizedString` object, or `None`.
        """
        p_id = self.id
        convert_to = None
        if isinstance(langs, str):
            langs = [langs]
            langs.extend(i18n.CONVERTERS.get(langs[0], ()))
            row = self.db.one("""
                SELECT content, lang
                  FROM statements
                  JOIN enumerate(%(langs)s::text[]) langs ON langs.value = statements.lang
                 WHERE participant = %(p_id)s
                   AND type = %(type)s
              ORDER BY langs.rank
                 LIMIT 1
            """, locals())
            if row and row.lang != langs[0]:
                if langs[0] in i18n.CONVERTERS.get(row.lang, ()):
                    convert_to = langs[0]
        else:
            conversions = {}
            for lang in langs:
                conversions[lang] = None
                converters = i18n.CONVERTERS.get(lang, ())
                for target_lang in converters:
                    if conversions.get(target_lang, '') is None:
                        conversions[lang] = target_lang
                    if lang in i18n.CONVERTERS.get(target_lang, ()):
                        conversions.setdefault(target_lang, lang)
                del converters
            langs = list(conversions.keys())
            row = self.db.one("""
                SELECT content, lang
                  FROM statements
             LEFT JOIN enumerate(%(langs)s::text[]) langs ON langs.value = statements.lang
                 WHERE participant = %(p_id)s
                   AND type = %(type)s
              ORDER BY langs.rank NULLS LAST, statements.id
                 LIMIT 1
            """, locals())
            if row:
                convert_to = conversions.get(row.lang)
            del conversions
        if row:
            content, lang = row
            del row
            if convert_to:
                try:
                    content = i18n.CONVERTERS[lang][convert_to](content)
                    # ↑ This is a potential source of serious vulnerabilities,
                    #   because it sends user input to third-party libraries.
                    lang = convert_to
                except Exception as e:
                    website.tell_sentry(e)
            return LocalizedString(content, lang)

    def get_statement_langs(self, type='profile', include_conversions=False):
        langs = self.db.all("""
            SELECT lang FROM statements WHERE participant=%s AND type=%s
        """, (self.id, type))
        if include_conversions:
            langs_set = set(langs)
            for lang in langs:
                converters = i18n.CONVERTERS.get(lang)
                if converters:
                    langs_set.update(converters.keys())
                    if any(len(l) > len(lang) for l in converters.keys()):
                        langs_set.remove(lang)
            langs[:] = langs_set
            del langs_set
        return langs

    def upsert_statement(self, lang, statement, type='profile'):
        if not statement:
            self.db.run("""
                DELETE FROM statements
                 WHERE participant=%s
                   AND type=%s
                   AND lang=%s
            """, (self.id, type, lang))
            return
        search_conf = i18n.SEARCH_CONFS.get(lang, 'simple')
        self.db.run("""
            INSERT INTO statements
                        (lang, content, participant, search_conf, type, ctime, mtime)
                 VALUES (%s, %s, %s, %s, %s, now(), now())
            ON CONFLICT (participant, type, lang) DO UPDATE
                    SET content = excluded.content
                      , mtime = excluded.mtime
        """, (lang, statement, self.id, search_conf, type))


    # Stubs
    # =====

    def resolve_stub(self):
        rec = self.db.one("""
            SELECT platform, user_id, user_name, domain
              FROM elsewhere
             WHERE participant = %s
        """, (self.id,))
        if rec:
            if rec.user_name:
                slug = urlquote(rec.user_name) + ('@' + rec.domain if rec.domain else '')
            else:
                slug = '~' + urlquote(rec.user_id) + (':' + rec.domain if rec.domain else '')
            return '/on/%s/%s/' % (rec.platform, slug)
        return None


    # Closing
    # =======

    def close(self):
        """Close the participant's account.
        """
        with self.db.get_cursor() as cursor:
            self.clear_tips_giving(cursor)
            self.clear_takes(cursor)
            if self.kind == 'group':
                self.remove_all_members(cursor)
            self.clear_subscriptions(cursor)
            self.update_status('closed', cursor)

    def clear_tips_giving(self, cursor):
        """Turn off the renewal of all tips from a given user.
        """
        tippees = cursor.all("""
            INSERT INTO tips
                      ( ctime, tipper, tippee, amount, period, periodic_amount
                      , paid_in_advance, is_funded, renewal_mode, visibility )
                 SELECT ctime, tipper, tippee, amount, period, periodic_amount
                      , paid_in_advance, is_funded, 0, visibility
                   FROM current_tips
                  WHERE tipper = %s
                    AND renewal_mode > 0
              RETURNING ( SELECT p FROM participants p WHERE p.id = tippee ) AS tippee
        """, (self.id,))
        for tippee in tippees:
            tippee.update_receiving(cursor=cursor)

    def clear_takes(self, cursor):
        """Leave all teams by zeroing all takes.
        """
        teams = cursor.all("""
            SELECT p.*::participants
              FROM current_takes x
              JOIN participants p ON p.id = x.team
             WHERE member=%s
        """, (self.id,))
        for t in teams:
            t.set_take_for(self, None, self, cursor=cursor)

    def clear_subscriptions(self, cursor):
        """Unsubscribe from all newsletters.
        """
        cursor.run("""
            UPDATE subscriptions
               SET is_on = false
                 , mtime = current_timestamp
             WHERE subscriber = %s
        """, (self.id,))

    def erase_personal_information(self):
        """Erase forever the user's personal data (statements, goal, etc).
        """
        r = self.db.one("""

            DELETE FROM community_memberships WHERE participant=%(id)s;
            DELETE FROM subscriptions WHERE subscriber=%(id)s;
            UPDATE emails
               SET participant = NULL
                 , verified = NULL
             WHERE participant = %(id)s
               AND address <> %(email)s;
            DELETE FROM notifications WHERE participant=%(id)s;
            DELETE FROM statements WHERE participant=%(id)s;

            DELETE FROM events
             WHERE participant = %(id)s
               AND (recorder IS NULL OR recorder = participant)
               AND type NOT IN (
                       'account-kind-change',
                       'mangopay-account-change',
                       'set_status'
                   );

            UPDATE participants
               SET avatar_url=NULL
                 , avatar_src=NULL
                 , avatar_email=NULL
                 , public_name=NULL
             WHERE id=%(id)s
         RETURNING *;

        """, dict(id=self.id, email=self.get_email_address(allow_disavowed=True)))
        self.set_attributes(**r._asdict())
        self.add_event(self.db, 'erase_personal_information', None)

    def invalidate_exchange_routes(self):
        """Disable any saved payment routes (cards, bank accounts).
        """
        routes = self.db.all("""
            SELECT r
              FROM exchange_routes r
             WHERE participant = %s
               AND status = 'chargeable'
        """, (self.id,))
        for route in routes:
            route.invalidate()

    def store_feedback(self, feedback):
        """Store feedback in database if provided by user
        """
        feedback = '' if feedback is None else feedback.strip()
        if feedback:
            self.db.run("""
                INSERT INTO feedback
                            (participant, feedback)
                     VALUES (%s, %s)
                ON CONFLICT (participant) DO UPDATE
                        SET feedback = excluded.feedback
                          , ctime = excluded.ctime
            """, (self.id, feedback))

    @classmethod
    def delete_old_feedback(cls):
        """Delete old user feedback.
        """
        n = cls.db.one("""
            WITH deleted AS (
                DELETE FROM feedback
                 WHERE ctime < current_date - interval '1 year'
                   AND coalesce((
                           SELECT status = 'active'
                             FROM participants
                            WHERE id = feedback.participant
                       ), true)
             RETURNING 1
            ) SELECT count(*) FROM deleted
        """)
        if n:
            website.logger.info(f"Deleted {n} old feedbacks.")

    @cached_property
    def closed_time(self):
        return self.db.one("""
            SELECT ts
              FROM events
             WHERE participant=%s
               AND type='set_status'
               AND payload='"closed"'
          ORDER BY ts DESC
             LIMIT 1
        """, (str(self.id),))


    # Deleting
    # ========

    def delete(self):
        if self.status != 'closed':
            self.close()
        with self.db.get_cursor() as cursor:
            cursor.run("""
                UPDATE emails SET participant = NULL, verified = NULL WHERE participant = %(p_id)s;
                DELETE FROM events WHERE participant = %(p_id)s;
                DELETE FROM user_secrets
                      WHERE participant = %(p_id)s
                        AND id >= 1
                        AND mtime <= (current_timestamp - %(SESSION_TIMEOUT)s);
                DELETE FROM participants WHERE id = %(p_id)s;
            """, dict(p_id=self.id, SESSION_TIMEOUT=SESSION_TIMEOUT))


    # Emails
    # ======

    def add_email(self, email, cursor=None):
        """
            This is called when
            1) Adding a new email address
            2) Resending the verification email for an unverified email address

            Returns the number of emails sent.
        """

        if not isinstance(email, NormalizedEmailAddress):
            email = normalize_email_address(email)

        # Check that this address isn't already verified
        owner = (cursor or self.db).one("""
            SELECT participant
              FROM emails
             WHERE lower(address) = lower(%(email)s)
               AND verified IS true
        """, locals())
        if owner:
            if owner == self.id:
                return 0
            else:
                raise EmailAlreadyTaken(email)

        addresses = set((cursor or self.db).all("""
            SELECT lower(address)
              FROM emails
             WHERE participant = %s
        """, (self.id,)))
        if email.lower() not in addresses and len(addresses) > 9:
            raise TooManyEmailAddresses(email)

        old_email = self.get_email_address(allow_disavowed=True)

        with self.db.get_cursor(cursor) as c:
            email_row = c.one("""
                INSERT INTO emails AS e
                            (address, nonce, added_time, participant)
                     VALUES (%s, %s, current_timestamp, %s)
                ON CONFLICT (participant, lower(address)) DO UPDATE
                        SET added_time = (CASE
                                WHEN e.verified IS true OR e.disavowed IS true
                                THEN e.added_time
                                ELSE excluded.added_time
                            END)
                          , address = excluded.address
                          , nonce = coalesce(e.nonce, excluded.nonce)
                  RETURNING *
            """, (email, str(uuid.uuid4()), self.id))
            if email_row.disavowed:
                raise EmailAddressIsBlacklisted(
                    email, 'complaint', email_row.disavowed_time, 'disavowed'
                )
            if email_row.verified:
                return 0
            # Limit number of verification emails per address
            self.db.hit_rate_limit('add_email.target', email, VerificationEmailAlreadySent)
            # Limit number of verification emails per participant
            self.db.hit_rate_limit('add_email.source', self.id, TooManyEmailVerifications)
            # Log event
            self.add_event(c, 'add_email', email)

        self.send_email('verification', email_row, old_email=old_email)

        if self.email:
            primary_email_row = self.get_email(self.email, cursor=cursor)
            self.send_email('verification_notice', primary_email_row, new_email=email)
            return 2
        else:
            self.update_avatar(cursor=cursor)

        return 1

    def update_email(self, email):
        if not getattr(self.get_email(email), 'verified', False):
            raise EmailNotVerified(email)
        check_email_blacklist(email, check_domain=False)
        p_id = self.id
        current_session_id = getattr(self.session, 'id', 0)
        with self.db.get_cursor() as c:
            self.add_event(c, 'set_primary_email', email)
            c.run("""
                UPDATE participants
                   SET email = %(email)s
                 WHERE id = %(p_id)s;

                DELETE FROM user_secrets
                 WHERE participant = %(p_id)s
                   AND id >= 1001 AND id <= 1010
                   AND id <> %(current_session_id)s
                   AND secret LIKE '%%.em';
            """, locals())
        self.set_attributes(email=email)
        self.update_avatar()
        stripe_customer_id = self.db.one("""
            SELECT remote_user_id
              FROM exchange_routes
             WHERE participant = %s
               AND network::text LIKE 'stripe-%%'
             LIMIT 1
        """, (self.id,))
        if stripe_customer_id:
            try:
                stripe.Customer.modify(stripe_customer_id, email=email)
            except Exception as e:
                website.tell_sentry(e)

    def verify_email(self, email_id, nonce, user, request):
        """Set an email address as verified, if the given nonce is valid.

        If the verification succeeds and the participant doesn't already have a
        primary email address, then the verified address becomes the primary.

        This function is designed not to leak information: attackers should not
        be able to use it to learn something they don't already know, for
        example whether a specific email address or ID is tied to a specific
        Liberapay account.
        """
        assert type(email_id) is int
        if not nonce:
            return EmailVerificationResult.FAILED
        with self.db.get_cursor() as cursor:
            r = cursor.one("""
                SELECT *
                  FROM emails
                 WHERE participant = %s
                   AND id = %s
                   FOR UPDATE
            """, (self.id, email_id))
            if r is None:
                return EmailVerificationResult.FAILED
            if r.nonce is None:
                if r.verified and user and user.controls(self):
                    return EmailVerificationResult.REDUNDANT
                else:
                    return EmailVerificationResult.FAILED
            if not constant_time_compare(r.nonce, nonce):
                return EmailVerificationResult.FAILED
            if r.verified:
                return EmailVerificationResult.REDUNDANT
            if (utcnow() - r.added_time) > EMAIL_VERIFICATION_TIMEOUT:
                # The timeout is meant to prevent an attacker who has gained access
                # to a forgotten secondary email address to link it to the target's
                # account. As such, it doesn't apply when the address isn't
                # secondary nor when the user is logged in.
                if user != self and len(self.get_emails()) > 1:
                    return EmailVerificationResult.LOGIN_REQUIRED
            try:
                cursor.run("""
                    UPDATE emails
                       SET verified = NULL
                     WHERE lower(address) = lower(%s)
                       AND participant IS NULL;

                    UPDATE emails
                       SET verified = true
                         , verified_time = now()
                         , disavowed = false
                     WHERE participant = %s
                       AND id = %s
                """, (r.address, self.id, email_id))
            except IntegrityError:
                return EmailVerificationResult.STYMIED
            self.add_event(cursor, 'email_verified', dict(
                address=r.address,
                headers=get_recordable_headers(request),
            ), user.id)
        # At this point we assume that the user is in fact the owner of the email
        # address and has received the verification email, so we can remove the
        # address from our blacklist if it was mistakenly blocked.
        self.db.run("""
            UPDATE email_blacklist
               SET ignore_after = current_timestamp
             WHERE lower(address) = lower(%(address)s)
               AND (ignore_after IS NULL OR ignore_after > current_timestamp)
               AND (reason = 'bounce' AND ts > %(added_time)s
                                      AND ts < (%(added_time)s + interval '24 hours') OR
                    reason = 'complaint' AND details = 'disavowed')
        """, r._asdict())
        # Finally, we set this newly verified address as the primary one if it's
        # the one the account was created with recently, or if the account
        # doesn't have a primary email address yet.
        initial_address, added_recently = self.db.one("""
            SELECT address
                 , (added_time > (current_timestamp - interval '7 days')) AS added_recently
              FROM emails
             WHERE participant = %s
          ORDER BY added_time
             LIMIT 1
        """, (self.id,), default=(None, None))
        if not self.email or (r.address == initial_address and added_recently):
            self.update_email(r.address)
        return EmailVerificationResult.SUCCEEDED

    def get_email(self, email, cursor=None):
        return (cursor or self.db).one("""
            SELECT *
              FROM emails
             WHERE participant=%s
               AND lower(address)=%s
        """, (self.id, email.lower()))

    def get_emails(self):
        return self.db.all("""
            SELECT e.*
                 , ( SELECT count(b)
                       FROM email_blacklist b
                      WHERE lower(b.address) = lower(e.address)
                        AND (b.ignore_after IS NULL OR b.ignore_after > current_timestamp)
                   ) > 0 AS blacklisted
              FROM emails e
             WHERE e.participant=%s
          ORDER BY e.id
        """, (self.id,))

    def get_email_address(self, cursor=None, allow_disavowed=False):
        """
        Get the participant's "primary" email address, even if it hasn't been
        confirmed yet.
        """
        return self.email or (cursor or self.db).one("""
            SELECT address
              FROM emails e
             WHERE participant = %s
               AND ( %s OR disavowed IS NOT true )
          ORDER BY disavowed IS NOT true DESC
                 , ( SELECT count(b)
                       FROM email_blacklist b
                      WHERE lower(b.address) = lower(e.address)
                        AND (b.ignore_after IS NULL OR b.ignore_after > current_timestamp)
                   ) ASC
                 , added_time ASC
             LIMIT 1
        """, (self.id, allow_disavowed))

    @property
    def can_be_emailed(self):
        return any(not e.blacklisted and not e.disavowed for e in self.get_emails())

    def remove_email(self, address):
        if address == self.email:
            raise CannotRemovePrimaryEmail()
        with self.db.get_cursor() as c:
            self.add_event(c, 'remove_email', address)
            c.run("""
                UPDATE emails
                   SET participant = NULL
                     , verified = NULL
                 WHERE participant = %s
                   AND address = %s
            """, (self.id, address))
            n_left = c.one("SELECT count(*) FROM emails WHERE participant=%s", (self.id,))
            if n_left == 0:
                raise CannotRemovePrimaryEmail()

    def render_email(self, spt_name, email_row, context, locale):
        email = email_row.address
        context = context.copy()
        self.fill_notification_context(context)
        context['email'] = email
        i18n.add_helpers_to_context(context, locale)
        context['escape'] = lambda s: s
        context_html = context.copy()
        i18n.add_helpers_to_context(context_html, locale)
        context_html['escape'] = htmlescape
        spt = website.emails[spt_name]
        if spt_name == 'newsletter':
            def render(t, context):
                if t == 'text/html':
                    context['body'] = markdown.render(context['body']).strip()
                return spt[t].render(context).strip()
        else:
            base_spt = None if spt_name.startswith('once/') else 'base'
            base_spt = context.get('base_spt', base_spt)
            base_spt = website.emails[base_spt] if base_spt else None
            bodies = {}
            def render(t, context):
                b = base_spt[t].render(context).strip() if base_spt else '$body'
                if t == 'text/plain' and t not in spt:
                    body = html2text(bodies['text/html']).strip()
                else:
                    body = spt[t].render(context).strip()
                bodies[t] = body
                return b.replace('$body', body)
        message = {}
        message['from_email'] = 'Liberapay Support <support@liberapay.com>'
        if spt_name == 'newsletter':
            message['from_email'] = 'Liberapay Newsletters <newsletters@liberapay.com>'
        if self.username[0] != '~':
            name = self.username
        else:
            name = (self.get_current_identity() or {}).get('name')
        message['to'] = [formataddr((name, email))]
        message['subject'] = spt['-/subject'].render(context).strip()
        self._rendering_email_to, self._email_session = email_row, None
        message['html'] = render('text/html', context_html)
        message['text'] = render('text/plain', context)
        del self._rendering_email_to, self._email_session
        partial_translation = locale.language.split('_', 1)[0] != 'en' and bool(
            context.get('partial_translation') or
            context_html.get('partial_translation')
        )
        return message, partial_translation

    def send_email(self, spt_name, email_row, **context):
        email = email_row.address
        check_email_blacklist(email, check_domain=False)
        if email_row.disavowed:
            raise EmailAddressIsBlacklisted(email, 'complaint', email_row.disavowed_time, 'disavowed')
        langs = i18n.parse_accept_lang(self.email_lang or 'en')
        locale = i18n.match_lang(langs)
        message, partial_translation = self.render_email(
            spt_name, email_row, context, locale
        )
        if partial_translation:
            message, partial_translation = self.render_email(
                spt_name, email_row, context, website.locales['en']
            )
            try:
                assert not partial_translation, \
                    f"unexpected `partial_translation` value: {partial_translation}"
            except AssertionError as e:
                website.tell_sentry(e)

        with email_lock:
            try:
                website.mailer.send(**message)
            except Exception as e:
                website.tell_sentry(e)
                try:
                    # Retry without the user's name in the `To:` header
                    message['to'] = [email]
                    website.mailer.send(**message)
                except Exception as e:
                    website.tell_sentry(e)
                    raise UnableToSendEmail(email)
            website.log_email(message)

    @classmethod
    def dequeue_emails(cls):
        fetch_messages = lambda last_id: cls.db.all("""
            SELECT *
              FROM notifications
             WHERE id > %s
               AND email AND email_status = 'queued'
          ORDER BY id ASC
             LIMIT 60
        """, (last_id,))
        def dequeue(msg, status):
            try:
                return cls.db.run(
                    "UPDATE notifications SET email_status = %(status)s WHERE id = %(id)s",
                    dict(id=msg.id, status=status)
                )
            except Exception as e:
                website.tell_sentry(e)
                sleep(5)
                return dequeue(msg, status)
        last_id = 0
        while True:
            messages = fetch_messages(last_id)
            if not messages:
                break
            for msg in messages:
                try:
                    r = cls.db.one("""
                        UPDATE notifications
                           SET email_status = 'sending'
                         WHERE id = %s
                           AND email_status = 'queued'
                     RETURNING email_status
                    """, (msg.id,))
                except ReadOnlySqlTransaction:
                    # The database is in read-only mode, give up for now
                    return
                if not r:
                    # Message already (being) sent by another thread
                    continue
                d = deserialize(msg.context)
                d['notification_ts'] = msg.ts
                p = cls.from_id(msg.participant)
                email = d.get('email') or p.email
                if not email or p.status != 'active':
                    dequeue(msg, 'skipped')
                    continue
                email_row = p.get_email(email)
                try:
                    p.send_email(msg.event, email_row, **d)
                except EmailAddressIsBlacklisted:
                    dequeue(msg, 'skipped')
                except Exception as e:
                    website.tell_sentry(e)
                    dequeue(msg, 'failed')
                else:
                    dequeue(msg, 'sent')
                sleep(1)
            last_id = messages[-1].id
        # Delete old email-only notifications
        cls.db.run("""
            DELETE FROM notifications
             WHERE NOT web
               AND ts <= (current_timestamp - interval '90 days')
        """)

    def set_email_lang(self, lang, cursor=None):
        with self.db.get_cursor(cursor=cursor) as c:
            c.run(
                "UPDATE participants SET email_lang=%s WHERE id=%s",
                (lang, self.id)
            )
            self.add_event(c, 'set_email_lang', lang)
        self.set_attributes(email_lang=lang)


    # Notifications
    # =============

    def notify(self, event, force_email=False, email=True, web=True, idem_key=None,
               email_unverified_address=False, **context):
        if email and not force_email:
            bit = EVENTS.get(event.split('~', 1)[0]).bit
            email = self.email_notif_bits & bit > 0
            if not email and not web:
                return
        p_id = self.id
        # If email_unverified_address is on, allow sending to an unverified email address.
        if email_unverified_address and not self.email:
            context['email'] = self.get_email_address()
        context = serialize(context)
        with self.db.get_cursor() as cursor:
            # Check that this notification isn't a duplicate
            n = cursor.one("""
                LOCK TABLE notifications IN SHARE ROW EXCLUSIVE MODE;
                SELECT count(*)
                  FROM notifications
                 WHERE participant = %(p_id)s
                   AND event = %(event)s
                   AND ( idem_key = %(idem_key)s OR
                         ts::date = current_date AND context = %(context)s )
            """, locals())
            if n > 0:
                raise DuplicateNotification(p_id, event, idem_key)
            # Okay, add the notification to the queue
            email_status = 'queued' if email else None
            n_id = cursor.one("""
                INSERT INTO notifications
                            (participant, event, context, web, email, email_status, idem_key)
                     VALUES (%(p_id)s, %(event)s, %(context)s, %(web)s, %(email)s, %(email_status)s, %(idem_key)s)
                  RETURNING id;
            """, locals())
        if not web:
            return n_id
        self.set_attributes(pending_notifs=self.pending_notifs + 1)
        return n_id

    def mark_notification_as_read(self, n_id):
        p_id = self.id
        r = self.db.one("""
            UPDATE notifications
               SET is_new = false
             WHERE participant = %(p_id)s
               AND id = %(n_id)s
               AND is_new
               AND web;
            SELECT pending_notifs FROM participants WHERE id = %(p_id)s;
        """, locals())
        self.set_attributes(pending_notifs=r)

    def mark_notifications_as_read(self, event=None, until=None, idem_key=None):
        if not self.pending_notifs:
            return
        p_id = self.id
        sql_filter = 'AND event = %(event)s' if event else ''
        if until:
            sql_filter += ' AND id <= %(until)s'
        if idem_key:
            sql_filter += ' AND idem_key = %(idem_key)s'
        r = self.db.one("""
            UPDATE notifications
               SET is_new = false
             WHERE participant = %(p_id)s
               AND is_new
               AND web
               {0};
            SELECT pending_notifs FROM participants WHERE id = %(p_id)s;
        """.format(sql_filter), locals())
        self.set_attributes(pending_notifs=r)

    def remove_notification(self, n_id):
        p_id = self.id
        r = self.db.one("""
            UPDATE notifications
               SET is_new = false
                 , hidden_since = current_timestamp
             WHERE id = %(n_id)s
               AND participant = %(p_id)s
               AND web;
            SELECT pending_notifs FROM participants WHERE id = %(p_id)s;
        """, locals())
        self.set_attributes(pending_notifs=r)

    def restore_notification(self, n_id):
        self.db.run("""
            UPDATE notifications
               SET hidden_since = NULL
             WHERE id = %(n_id)s
               AND participant = %(p_id)s
               AND hidden_since IS NOT NULL
        """, dict(n_id=n_id, p_id=self.id))

    def fill_notification_context(self, context):
        context.update(aspen_jinja2_renderer.Renderer.global_context)
        context['website'] = website
        context['participant'] = self
        context['username'] = self.username
        context['button_style'] = lambda variant: (
            "color: {text_color}; text-decoration: none; display: inline-block; "
            "padding: 0 16px; background: {bg_color}; white-space: nowrap; "
            "border: 1px solid {border_color}; border-radius: 3px; "
            "font: normal 16px/40px Ubuntu, Verdana, sans-serif;"
        ).format(
            bg_color=website.scss_variables['btn-' + variant + '-bg'],
            border_color=website.scss_variables['btn-' + variant + '-border'],
            text_color=website.scss_variables['btn-' + variant + '-color'],
        )
        context['LegacyMoney'] = i18n.LegacyMoney

    def get_notifs(self, before=None, limit=None, viewer=None):
        for_admin = bool(viewer and viewer.is_acting_as('admin'))
        p_id = self.id
        return self.db.all("""
            SELECT id, event, context, is_new, ts, hidden_since
              FROM notifications
             WHERE participant = %(p_id)s
               AND web
               AND coalesce(id < %(before)s, true)
               AND ( %(for_admin)s OR
                     hidden_since IS NULL OR
                     hidden_since > (current_timestamp - interval '6 hours') )
          ORDER BY id DESC
             LIMIT %(limit)s
        """, locals())

    def render_notifications(self, state, notifs=None, before=None, limit=None, viewer=None):
        """Render notifications as HTML.

        The `notifs` argument allows rendering arbitrary notifications.

        """
        notifs = notifs or self.get_notifs(before=before, limit=limit, viewer=viewer)

        r = []
        for id, event, notif_context, is_new, ts, hidden_since in notifs:
            d = dict(id=id, is_new=is_new, ts=ts, hidden_since=hidden_since)
            r.append(d)
            try:
                notif_context = deserialize(notif_context)
                d['type'] = notif_context.get('type', 'info')
                spt = website.emails[event]
                context = dict(state)
                self.fill_notification_context(context)
                context.update(notif_context)
                context['notification_ts'] = ts
                d['subject'] = spt['-/subject'].render(context).strip()
                d['html'] = spt['text/html'].render(context).strip()
            except Exception as e:
                d['sentry_ident'] = website.tell_sentry(e).get('sentry_ident')
        return r

    @classmethod
    def notify_patrons(cls):
        grouped_tips = cls.db.all("""
            SELECT (elsewhere, tippee_p)::elsewhere_with_participant AS account_elsewhere
                 , json_agg(tip) AS tips
              FROM current_tips tip
              JOIN events event ON event.participant = tip.tippee
                               AND event.type = 'take-over'
              JOIN elsewhere ON elsewhere.participant = tip.tippee
                            AND elsewhere.platform = event.payload->>'platform'
                            AND elsewhere.user_id = event.payload->>'user_id'
                            AND elsewhere.domain = event.payload->>'domain'
              JOIN participants tippee_p ON tippee_p.id = tip.tippee
              JOIN participants tipper_p ON tipper_p.id = tip.tipper
             WHERE tip.renewal_mode > 0
               AND tip.paid_in_advance IS NULL
               AND tippee_p.payment_providers > 0
               AND tippee_p.join_time >= (current_date - interval '30 days')
               AND tippee_p.status = 'active'
               AND tipper_p.status = 'active'
               AND tippee_p.is_suspended IS NOT TRUE
               AND tipper_p.is_suspended IS NOT TRUE
               AND ( tippee_p.goal IS NULL OR tippee_p.goal >= 0 )
               AND event.ts < (current_timestamp - interval '6 hours')
               AND EXISTS (
                       SELECT 1
                         FROM tips old_tip
                         JOIN participants old_tippee ON old_tippee.id = old_tip.tippee
                        WHERE old_tip.tipper = tip.tipper
                          AND old_tip.tippee = (event.payload->>'owner')::int
                          AND old_tippee.status = 'stub'
                   )
               AND NOT EXISTS (
                       SELECT 1
                         FROM notifications n
                        WHERE n.participant = tip.tipper
                          AND n.event = 'pledgee_joined~v2'
                          AND n.idem_key = tip.tippee::text
                   )
          GROUP BY elsewhere.id, tippee_p.id
        """)
        for elsewhere, tips in grouped_tips:
            cls._notify_patrons(elsewhere, tips)

    @classmethod
    def _notify_patrons(cls, elsewhere, tips):
        assert elsewhere.participant.payment_providers > 0
        for tip in tips:
            tipper = Participant.from_id(tip['tipper'])
            if tip['paid_in_advance'] is None and tip['renewal_mode'] == 2:
                # Trick `schedule_renewals` into believing that this donation is
                # awaiting renewal, when in fact it's awaiting its first payment.
                cls.db.run("""
                    WITH latest_tip AS (
                             SELECT *
                               FROM tips
                              WHERE tipper = %(tipper)s
                                AND tippee = %(tippee)s
                           ORDER BY mtime DESC
                              LIMIT 1
                         )
                    UPDATE tips t
                       SET paid_in_advance = zero(t.amount)
                      FROM latest_tip lt
                     WHERE t.tipper = lt.tipper
                       AND t.tippee = lt.tippee
                       AND t.mtime >= lt.mtime
                       AND t.paid_in_advance IS NULL
                """, tip)
            schedule = tipper.schedule_renewals()
            sp = next((
                sp for sp in schedule
                if any(tr['tippee_id'] == tip['tippee'] for tr in sp.transfers)
            ), None)
            tipper.notify(
                'pledgee_joined~v2',
                idem_key=str(elsewhere.participant.id),
                user_name=elsewhere.user_name,
                platform=elsewhere.platform_data.display_name,
                pledge_date=parse_date(tip['ctime']).date(),
                periodic_amount=Money(**tip['periodic_amount']),
                elsewhere_profile_url=elsewhere.html_url,
                join_time=elsewhere.participant.join_time,
                liberapay_profile_url=elsewhere.participant.url(),
                liberapay_username=elsewhere.participant.username,
                tippee_id=elsewhere.participant.id,
                scheduled_payin=sp,
                email_unverified_address=bool(sp),
            )
            if sp:
                cls.db.run("""
                    UPDATE scheduled_payins
                       SET notifs_count = notifs_count + 1
                         , last_notif_ts = current_timestamp
                     WHERE id = %s
                """, (sp.id,))


    # Events
    # ======

    def add_event(self, c, type, payload, recorder=None):
        if recorder is None:
            state = website.state.get(None)
            if state:
                recorder = getattr(state.get('user'), 'id', None)
        return c.one("""
            INSERT INTO events
                        (participant, type, payload, recorder)
                 VALUES (%s, %s, %s, %s)
              RETURNING *
        """, (self.id, type, json.dumps(payload), recorder))

    def get_last_event_of_type(self, type):
        return self.db.one("""
            SELECT *
              FROM events
             WHERE participant = %s
               AND type = %s
          ORDER BY ts DESC
             LIMIT 1
        """, (self.id, type))


    # Newsletters
    # ===========

    def upsert_subscription(self, on, publisher):
        subscriber = self.id
        if on:
            token = str(uuid.uuid4())
            return self.db.one("""
                INSERT INTO subscriptions
                            (publisher, subscriber, is_on, token)
                     VALUES (%(publisher)s, %(subscriber)s, %(on)s, %(token)s)
                ON CONFLICT (publisher, subscriber) DO UPDATE
                        SET is_on = excluded.is_on
                          , mtime = current_timestamp
                  RETURNING *
            """, locals())
        else:
            return self.db.one("""
                UPDATE subscriptions
                   SET is_on = %(on)s
                     , mtime = CURRENT_TIMESTAMP
                 WHERE publisher = %(publisher)s
                   AND subscriber = %(subscriber)s
             RETURNING *
            """, locals())

    def check_subscription_status(self, subscriber):
        return self.db.one("""
            SELECT is_on
              FROM subscriptions
             WHERE publisher = %s AND subscriber = %s
        """, (self.id, subscriber.id))

    @classmethod
    def get_subscriptions(cls, publisher):
        unsub_url = '{}/~{}/unsubscribe?id=%s&token=%s'.format(website.canonical_url, publisher)
        return cls.db.all("""
            SELECT s.*
                 , format(%(unsub_url)s, s.id, s.token) AS unsubscribe_url
              FROM subscriptions s
             WHERE s.publisher = %(publisher)s
        """, locals())

    @classmethod
    def send_newsletters(cls):
        fetch_messages = lambda: cls.db.all("""
            SELECT n.sender
                 , row_to_json((SELECT a FROM (
                        SELECT t.newsletter, t.lang, t.subject, t.body
                   ) a)) AS context
              FROM newsletter_texts t
              JOIN newsletters n ON n.id = t.newsletter
             WHERE scheduled_for <= now() + INTERVAL '30 seconds'
               AND sent_at IS NULL
          ORDER BY scheduled_for ASC
        """)
        while True:
            messages = fetch_messages()
            if not messages:
                break
            for msg in messages:
                with cls.db.get_cursor() as cursor:
                    count = 0
                    for s in cls.get_subscriptions(msg.sender):
                        context = dict(msg.context, unsubscribe_url=s.unsubscribe_url)
                        count += cursor.one("""
                            INSERT INTO notifications
                                        (participant, event, context, web, email, email_status)
                                 SELECT p.id, 'newsletter', %s, false, true, 'queued'
                                   FROM participants p
                                  WHERE p.id = %s
                                    AND p.email IS NOT NULL
                         RETURNING count(*)
                        """, (serialize(context), s.subscriber))
                    assert cursor.one("""
                        UPDATE newsletter_texts
                           SET sent_at = now()
                             , sent_count = %s
                         WHERE id = %s
                     RETURNING sent_at
                    """, (count, msg.id))
                sleep(1)


    # Recipient settings
    # ==================

    @cached_property
    def recipient_settings(self):
        r = self.db.one("""
            SELECT *
              FROM recipient_settings
             WHERE participant = %s
        """, (self.id,), default=Object(
            participant=self.id,
            patron_visibilities=(7 if self.status == 'stub' else None),
            patron_countries=None,
        ))
        if r.patron_countries:
            if r.patron_countries.startswith('-'):
                r.patron_countries = set(i18n.COUNTRIES) - set(r.patron_countries[1:].split(','))
            else:
                r.patron_countries = set(r.patron_countries.split(','))
        return r

    def update_recipient_settings(self, **kw):
        cols, vals = zip(*kw.items())
        updates = ','.join('{0}=excluded.{0}'.format(col) for col in cols)
        cols = ', '.join(cols)
        placeholders = ', '.join(['%s']*len(vals))
        with self.db.get_cursor() as cursor:
            settings = cursor.one("""
                INSERT INTO recipient_settings
                            (participant, {0})
                     VALUES (%s, {1})
                ON CONFLICT (participant) DO UPDATE
                        SET {2}
                  RETURNING *
            """.format(cols, placeholders, updates), (self.id,) + vals)
            self.add_event(cursor, 'recipient_settings', kw)
        self.recipient_settings = settings


    # Random Stuff
    # ============

    def url(self, path='', query='', log_in='auto', log_in_with_secondary=False):
        """Return the full canonical URL of a user page.

        Args:
            path (str):
                the path to the user page. The default value (empty
                string) leads to the user's public profile page.
            query (dict):
                querystring parameters to add to the URL.
            log_in (str):
                Include an email session token in the URL. This only works when
                called from inside an email simplate.
                When set to 'required', the user will see an error page if the
                log-in token is too old, whereas the default value 'auto' will
                result in an expired token being ignored.
                When set to 'no', log-in parameters aren't added to the URL.
            log_in_with_secondary (bool):
                whether to allow logging in with a secondary email address
        """
        scheme = website.canonical_scheme
        host = website.canonical_host
        username = self.username
        if query:
            query = '?' + urlencode(query, doseq=True)
        if log_in not in ('auto', 'required', 'no'):
            raise ValueError(f"{log_in!r} isn't a valid value for the `log_in` argument")
        if self.kind not in ('individual', 'organization'):
            if log_in == 'required':
                raise ValueError(f"{log_in=} isn't valid when participant kind is {self.kind!r}")
            log_in = 'no'
        email_row = getattr(self, '_rendering_email_to', None)
        if email_row:
            extra_query = []
            if log_in == 'required' or log_in == 'auto' and not self.has_password:
                primary_email = self.get_email_address()
                allow_log_in = (
                    log_in_with_secondary or
                    primary_email and email_row.address.lower() == primary_email.lower()
                )
                if allow_log_in:
                    session = self._email_session
                    if not session:
                        try:
                            session = self.start_session(suffix='.em', id_min=1001, id_max=1010)
                        except AccountSuspended:
                            session = self.start_session(suffix='.ro', id_min=1001, id_max=1010)
                        self._email_session = session
                    if session:
                        extra_query.append(('log-in.id', self.id))
                        extra_query.append(('log-in.key', session.id))
                        extra_query.append(('log-in.token', session.secret))
                        if log_in != 'required':
                            extra_query.append(('log-in.required', 'no'))
                elif log_in == 'required':
                    raise AssertionError('%r != %r' % (email_row.address, primary_email))
            if not email_row.verified:
                if not email_row.nonce:
                    email_row = self._rendering_email_to = self.db.one("""
                        UPDATE emails
                           SET nonce = coalesce(nonce, %s)
                         WHERE id = %s
                     RETURNING *
                    """, (str(uuid.uuid4()), email_row.id))
                extra_query.append(('email.id', email_row.id))
                extra_query.append(('email.nonce', email_row.nonce))
            if extra_query:
                query += ('&' if query else '?') + urlencode(extra_query)
            del extra_query
        elif log_in == 'required':
            raise ValueError(
                "`log_in` is 'required' but `self._rendering_email_to` is missing"
            )
        if query and '?' in path:
            (path, query), extra_query = path.split('?', 1), query
            query = f'?{query}&{extra_query[1:]}'
        return f'{scheme}://{host}/{username}/{path}{query}'

    def get_teams(self):
        """Return a list of teams this user is a member of.
        """
        return self.db.all("""
            SELECT team_p
              FROM current_takes take
              JOIN participants team_p ON team_p.id = take.team
             WHERE take.member = %s
        """, (self.id,))

    def get_teams_data_for_display(self, locale):
        return self.db.all("""
            SELECT team_p AS participant
                 , take.team AS id
                 , ( SELECT s.content
                       FROM statements s
                      WHERE s.participant = take.team
                        AND s.type = 'summary'
                   ORDER BY s.lang = %s DESC, s.id
                      LIMIT 1
                   ) AS summary
                 , ( SELECT count(*)
                       FROM current_takes take2
                      WHERE take2.team = take.team
                    ) AS nmembers
              FROM current_takes take
              JOIN participants team_p ON team_p.id = take.team
             WHERE take.member = %s
          ORDER BY team_p.username
        """, (locale.language, self.id))

    @cached_property
    def team_names(self):
        return sorted(self.db.all("""
            SELECT team.username
              FROM current_takes take
              JOIN participants team ON team.id = take.team
             WHERE take.member = %s;
        """, (self.id,)))

    @property
    def accepts_tips(self):
        return self.status != 'closed' and ((self.goal is None) or (self.goal >= 0))


    # Communities
    # ===========

    def create_community(self, name, **kw):
        return Community.create(name, self, **kw)

    def upsert_community_membership(self, on, c_id, cursor=None):
        p_id = self.id
        if on:
            (cursor or self.db).run("""
                INSERT INTO community_memberships
                            (community, participant, is_on)
                     VALUES (%(c_id)s, %(p_id)s, %(on)s)
                ON CONFLICT (participant, community) DO UPDATE
                        SET is_on = excluded.is_on
                          , mtime = current_timestamp
            """, locals())
        else:
            (cursor or self.db).run("""
                UPDATE community_memberships
                   SET is_on = %(on)s
                     , mtime = current_timestamp
                 WHERE community = %(c_id)s
                   AND participant = %(p_id)s;
            """, locals())

    def get_communities(self):
        return self.db.all("""
            SELECT c.*, replace(c.name, '_', ' ') AS pretty_name
              FROM community_memberships cm
              JOIN communities c ON c.id = cm.community
             WHERE cm.is_on AND cm.participant = %s
          ORDER BY c.nmembers ASC, c.name
        """, (self.id,))


    # Invoices
    # ========

    def can_invoice(self, other):
        if self.kind != 'individual' or other.kind != 'organization':
            return False
        return bool(self.allow_invoices and other.allow_invoices)

    def update_invoice_status(self, invoice_id, new_status, message=None):
        if new_status in ('canceled', 'new', 'retracted'):
            column = 'sender'
        elif new_status in ('accepted', 'paid', 'rejected'):
            column = 'addressee'
        else:
            raise ValueError(new_status)
        if new_status in ('new', 'canceled'):
            old_status = 'pre'
        elif new_status == 'paid':
            old_status = 'accepted'
        else:
            old_status = 'new'
        with self.db.get_cursor() as c:
            p_id = self.id
            r = c.one("""
                UPDATE invoices
                   SET status = %(new_status)s
                 WHERE id = %(invoice_id)s
                   AND status = %(old_status)s
                   AND {0} = %(p_id)s
             RETURNING id
            """.format(column), locals())
            if not r:
                return False
            c.run("""
                INSERT INTO invoice_events
                            (invoice, participant, status, message)
                     VALUES (%s, %s, %s, %s)
            """, (invoice_id, self.id, new_status, message))
        return True

    def pay_invoice(self, invoice):
        """
        This function used to transfer money between Mangopay wallets. It needs
        to be rewritten to implement other payment methods (e.g. PayPal, Wise,
        Stripe).
        """
        return False


    # Currencies
    # ==========

    @cached_property
    def accepted_currencies_set(self):
        v = self.accepted_currencies
        if v is None:
            return CURRENCIES
        v = set(v.split(','))
        if self.payment_providers == 2 and not PAYPAL_CURRENCIES.intersection(v):
            # The currency preferences are unsatisfiable, ignore them.
            v = PAYPAL_CURRENCIES
            self.__dict__['accepted_currencies_overwritten'] = True
        return v

    @cached_property
    def accepted_currencies_overwritten(self):
        self.accepted_currencies_set
        return self.__dict__.get('accepted_currencies_overwritten', False)

    def change_main_currency(self, new_currency, recorder):
        old_currency = self.main_currency
        p_id = self.id
        recorder_id = recorder.id
        with self.db.get_cursor() as cursor:
            if not recorder.is_acting_as('admin'):
                cursor.hit_rate_limit('change_currency', self.id, TooManyCurrencyChanges)
            r = cursor.one("""
                UPDATE participants
                   SET main_currency = %(new_currency)s
                     , goal = convert(goal, %(new_currency)s)
                     , giving = convert(giving, %(new_currency)s)
                     , receiving = convert(receiving, %(new_currency)s)
                     , taking = convert(taking, %(new_currency)s)
                 WHERE id = %(p_id)s
                   AND main_currency = %(old_currency)s
             RETURNING id
            """, locals())
            if not r:
                return
            self.set_attributes(main_currency=new_currency)
            self.add_event(cursor, 'change_main_currency', dict(
                new_currency=new_currency, old_currency=old_currency
            ), recorder=recorder_id)

    @staticmethod
    def get_currencies_for(tippee, tip):
        if isinstance(tippee, AccountElsewhere):
            tippee = tippee.participant
        tip_currency = tip.amount.currency
        accepted = tippee.accepted_currencies_set
        if tip_currency in accepted:
            return tip_currency, accepted
        else:
            fallback_currency = tippee.main_currency
            if fallback_currency not in accepted:
                fallback_currency = 'USD'
            return fallback_currency, accepted

    @cached_property
    def donates_in_multiple_currencies(self):
        return self.db.one("""
            SELECT count(DISTINCT amount::currency) > 1
              FROM current_tips
             WHERE tipper = %s
               AND amount > 0
               AND renewal_mode > 0
        """, (self.id,))


    # More Random Stuff
    # =================

    @staticmethod
    def check_username(suggested):
        if not suggested:
            raise UsernameIsEmpty(suggested)

        if len(suggested) > USERNAME_MAX_SIZE:
            raise UsernameTooLong(suggested)

        if set(suggested) - ASCII_ALLOWED_IN_USERNAME:
            raise UsernameContainsInvalidCharacters(suggested)

        if suggested.isdigit():
            raise UsernameIsPurelyNumerical(suggested)

        if suggested[0] == '.':
            raise UsernameBeginsWithRestrictedCharacter(suggested)

        suffix = suggested[suggested.rfind('.'):]
        if suffix in USERNAME_SUFFIX_BLACKLIST:
            raise UsernameEndsWithForbiddenSuffix(suggested, suffix)

        if suggested.lower() in website.restricted_usernames:
            raise UsernameIsRestricted(suggested)

    def change_username(self, suggested, cursor=None, recorder=None):
        if suggested != f'~{self.id}':
            self.check_username(suggested)
        recorder_id = getattr(recorder, 'id', None)

        if suggested != self.username:
            with self.db.get_cursor(cursor) as c:
                try:
                    # Will raise IntegrityError if the desired username is taken.
                    actual = c.one("""
                        UPDATE participants
                           SET username=%s
                         WHERE id=%s
                           AND username <> %s
                     RETURNING username, lower(username)
                    """, (suggested, self.id, suggested))
                except IntegrityError:
                    raise UsernameAlreadyTaken(suggested)
                if actual is None:
                    return suggested
                assert (suggested, suggested.lower()) == actual  # sanity check

                # Deal with redirections
                last_rename = self.get_last_event_of_type('set_username')
                if last_rename:
                    c.hit_rate_limit('change_username', self.id, TooManyUsernameChanges)
                    old_username = last_rename.payload
                    prefixes = {
                        'old': '/%s/' % old_username.lower(),
                        'new': '/%s/' % suggested.lower(),
                    }
                    # Delete and update previous redirections
                    c.run("""
                        DELETE FROM redirections WHERE from_prefix = %(new)s;
                        UPDATE redirections
                           SET to_prefix = %(new)s
                             , mtime = now()
                         WHERE to_prefix = %(old)s;
                    """, prefixes)
                    if prefixes['old'] != prefixes['new']:
                        # Add a redirection if the old name was in use long enough (1 hour)
                        active_period = utcnow() - last_rename.ts
                        if active_period.total_seconds() > 3600:
                            c.run("""
                                INSERT INTO redirections
                                            (from_prefix, to_prefix)
                                     VALUES (%(old)s, %(new)s)
                                ON CONFLICT (from_prefix) DO UPDATE
                                        SET to_prefix = excluded.to_prefix
                                          , mtime = now()
                            """, prefixes)

                self.add_event(c, 'set_username', suggested, recorder=recorder_id)
                self.set_attributes(username=suggested)

            if last_rename and self.kind == 'group':
                assert isinstance(recorder, Participant)
                members = self.db.all("""
                    SELECT p
                      FROM current_takes t
                      JOIN participants p ON p.id = t.member
                     WHERE t.team = %s
                """, (self.id,))
                for m in members:
                    if m != recorder:
                        m.notify(
                            'team_rename', email=False, web=True,
                            old_name=old_username, new_name=suggested,
                            renamed_by=recorder.username,
                        )

        return suggested

    def change_public_name(self, new_public_name, cursor=None, recorder=None):
        new_public_name = unicodedata.normalize('NFKC', new_public_name.strip())

        if len(new_public_name) > PUBLIC_NAME_MAX_SIZE:
            raise ValueTooLong(new_public_name, PUBLIC_NAME_MAX_SIZE)

        def is_char_forbidden(char):
            if char.isalnum() or char.isspace():
                return False
            # http://www.unicode.org/reports/tr44/tr44-4.html#General_Category_Values
            category = unicodedata.category(char)
            return category[:1] != 'P'

        bad_chars = [c for c in set(new_public_name) if is_char_forbidden(c)]
        if bad_chars:
            raise ValueContainsForbiddenCharacters(new_public_name, bad_chars)

        if new_public_name != self.public_name:
            if new_public_name == '':
                new_public_name = None
            with self.db.get_cursor(cursor) as c:
                r = c.one("""
                    UPDATE participants
                       SET public_name = %s
                     WHERE id = %s
                       AND coalesce(public_name, '') <> coalesce(%s, '')
                 RETURNING id
                """, (new_public_name, self.id, new_public_name))
                if r:
                    self.add_event(c, 'set_public_name', new_public_name)
                    self.set_attributes(public_name=new_public_name)

        return new_public_name

    def update_avatar(self, src=None, cursor=None, avatar_email=None, refresh=False):
        if self.status == 'stub':
            assert src is None

        src = self.avatar_src if src is None else src
        platform, user_id = src.split(':', 1) if src else (None, None)

        if avatar_email is None:
            avatar_email = self.avatar_email
        email = avatar_email or self.get_email_address(cursor)

        if platform == 'libravatar' or platform is None and email:
            if not email:
                return
            # https://wiki.libravatar.org/api/
            #
            # We only use the first SRV record that we choose; if there is an
            # error talking to that server, we give up, instead of retrying with
            # another record.  pyLibravatar does the same.
            normalized_email = email.strip().lower()
            avatar_origin = 'https://seccdn.libravatar.org'
            try:
                # Look up the SRV record to use.
                email_domain = normalized_email.rsplit('@', 1)[1]
                try:
                    srv_records = DNS.resolve('_avatars-sec._tcp.'+email_domain, 'SRV')
                    scheme = 'https'
                except Exception:
                    srv_records = DNS.resolve('_avatars._tcp.'+email_domain, 'SRV')
                    scheme = 'http'
                # Filter down to just the records with the "highest" `.priority`
                # (lower number = higher priority); for the libravatar API tells us:
                #
                # > Libravatar clients MUST only consider servers listed in the
                # > highest SRV priority.
                top_priority = min(rec.priority for rec in srv_records)
                srv_records = [rec for rec in srv_records if rec.priority == top_priority]
                # Of those, choose randomly based on their relative `.weight`s;
                # for the libravatar API tells us:
                #
                # > They MUST honour relative weights.
                #
                # RFC 2782 (at the top of page 4) gives us this algorithm for
                # randomly selecting a record based on the weights:
                srv_records.sort(key=attrgetter('weight'))  # ensure that .weight=0 recs are first in the list
                weight_choice = randint(0, sum(rec.weight for rec in srv_records))
                weight_sum = 0
                for rec in srv_records:
                    weight_sum += rec.weight
                    if weight_sum >= weight_choice:
                        choice_record = rec
                        break

                # Build the `avatar_origin` URL.
                # The Dnspython library has already validated that `.target` is
                # a valid DNS name and that `.port` is a uint16.
                host = choice_record.target.canonicalize().to_text(omit_final_dot=True)
                port = choice_record.port
                if port == 0:
                    # Port zero isn't supposed to be used and typically can't be. The
                    # Libravatar wiki doesn't clearly specify what to do in this case.
                    pass
                elif (scheme == 'http' and port != 80) or (scheme == 'https' and port != 443):
                    # Only include an explicit port number if it's not the default
                    # port for the scheme.
                    avatar_origin = '%s://%s:%d' % (scheme, host, port)
                else:
                    avatar_origin = '%s://%s' % (scheme, host)
            except DNSException:
                pass
            except Exception as e:
                website.tell_sentry(e)
            avatar_id = md5(normalized_email.encode('utf8')).hexdigest()
            avatar_url = avatar_origin + '/avatar/' + avatar_id

        elif platform is None:
            avatar_url = (cursor or self.db).one("""
                SELECT avatar_url
                  FROM elsewhere
                 WHERE participant = %s
              ORDER BY platform = 'github' DESC,
                       avatar_url LIKE '%%libravatar.org%%' DESC,
                       avatar_url LIKE '%%gravatar.com%%' DESC
                 LIMIT 1
            """, (self.id,))

        else:
            avatar_url = (cursor or self.db).one("""
                SELECT avatar_url
                  FROM elsewhere
                 WHERE participant = %s
                   AND platform = %s
                   AND coalesce(user_id = %s, true)
              ORDER BY id
                 LIMIT 1
            """, (self.id, platform, user_id or None))

        avatar_url = tweak_avatar_url(avatar_url, increment=refresh)
        check_url = (
            avatar_url and
            avatar_url != self.avatar_url and
            self.status != 'stub' and
            website.app_conf.check_avatar_urls
        )
        if check_url:
            # Check that the new avatar URL returns a 200.
            try:
                r = requests.head(avatar_url, allow_redirects=True, timeout=5)
                if r.status_code != 200:
                    avatar_url = None
            except requests.exceptions.RequestException:
                avatar_url = None
        if avatar_email == '':
            avatar_email = None
        self.set_attributes(**(cursor or self.db).one("""
            UPDATE participants
               SET avatar_url = coalesce(%s, avatar_url)
                 , avatar_src = %s
                 , avatar_email = %s
             WHERE id = %s
         RETURNING avatar_url, avatar_src, avatar_email
        """, (avatar_url, src, avatar_email, self.id))._asdict())

        return avatar_url

    def update_goal(self, goal, cursor=None):
        if goal is not None:
            goal = goal.convert_if_currency_is_phased_out()
            if goal.currency != self.main_currency:
                raise UnexpectedCurrency(goal, self.main_currency)
        with self.db.get_cursor(cursor) as c:
            r = c.one("""
                UPDATE participants
                   SET goal = %(new_goal)s
                 WHERE id = %(p_id)s
                   AND ( (goal IS NULL) <> (%(new_goal)s IS NULL) OR goal <> %(new_goal)s )
             RETURNING id
            """, dict(new_goal=goal, p_id=self.id))
            if r is None:
                return
            json = None if goal is None else str(goal)
            self.add_event(c, 'set_goal', json)
            self.set_attributes(goal=goal)
            if not self.accepts_tips:
                tippers = c.all("""
                    SELECT p
                      FROM current_tips t
                      JOIN participants p ON p.id = t.tipper
                     WHERE t.tippee = %s
                """, (self.id,))
                for tipper in tippers:
                    tipper.update_giving(cursor=c)
                r = c.one("""
                    UPDATE participants
                       SET receiving = zero(receiving)
                         , npatrons = 0
                     WHERE id = %s
                 RETURNING receiving, npatrons
                """, (self.id,))
                self.set_attributes(**r._asdict())

    def update_status(self, status, cursor=None):
        with self.db.get_cursor(cursor) as c:
            goal = None
            if status == 'closed':
                goal = Money(-1, self.main_currency)
            elif status == 'active':
                last_goal = self.get_last_event_of_type('set_goal')
                if last_goal and last_goal.payload:
                    try:
                        goal = Money.parse(last_goal.payload)
                    except Exception as e:
                        website.tell_sentry(e)
            r = c.one("""
                UPDATE participants
                   SET status = %(status)s
                     , join_time = COALESCE(join_time, CURRENT_TIMESTAMP)
                     , goal = convert(%(goal)s, main_currency)
                 WHERE id=%(id)s
             RETURNING status, join_time, goal
            """, dict(id=self.id, status=status, goal=goal))
            self.set_attributes(**r._asdict())
            self.add_event(c, 'set_status', status)
            if not self.accepts_tips:
                self.update_receiving(c)

    def get_giving_in(self, currency):
        return self.db.one("""
            SELECT sum(t.amount)
              FROM current_tips t
              JOIN participants p ON p.id = t.tippee
             WHERE t.tipper = %s
               AND t.amount::currency = %s
               AND p.status = 'active'
               AND (p.goal IS NULL OR p.goal >= 0)
        """, (self.id, currency)) or Money.ZEROS[currency]

    def get_receiving_in(self, currency, cursor=None):
        r = (cursor or self.db).one("""
            SELECT sum(t.amount)
              FROM current_tips t
             WHERE t.tippee = %s
               AND t.amount::currency = %s
               AND t.is_funded
        """, (self.id, currency)) or Money.ZEROS[currency]
        if currency not in CURRENCIES:
            raise ValueError(currency)
        r += Money((cursor or self.db).one("""
            SELECT sum(t.actual_amount->%s)
              FROM current_takes t
             WHERE t.member = %s
        """, (currency, self.id)) or Money.ZEROS[currency].amount, currency)
        return r

    def get_exact_receiving(self):
        return self.db.one("""
            SELECT basket_sum(t.amount)
              FROM current_tips t
             WHERE t.tippee = %s
               AND t.is_funded
        """, (self.id,))

    def update_giving_and_tippees(self, cursor):
        updated_tips = self.update_giving(cursor)
        for tip in updated_tips:
            Participant.from_id(tip.tippee).update_receiving(cursor)

    def update_giving(self, cursor=None):
        # Update is_funded on tips
        tips = (cursor or self.db).all("""
            SELECT t.*, p2.status AS tippee_status, p2.goal AS tippee_goal
              FROM current_tips t
              JOIN participants p2 ON p2.id = t.tippee
             WHERE t.tipper = %s
        """, (self.id,))
        has_donated_recently = (cursor or self.db).one("""
            SELECT DISTINCT tr.tipper AS x
              FROM transfers tr
             WHERE tr.tipper = %(p_id)s
               AND tr.context IN ('tip', 'take')
               AND tr.timestamp > (current_timestamp - interval '30 days')
               AND tr.status = 'succeeded'
             UNION
            SELECT DISTINCT pi.payer AS x
              FROM payins pi
             WHERE pi.payer = %(p_id)s
               AND pi.ctime > (current_timestamp - interval '30 days')
               AND pi.status = 'succeeded'
        """, dict(p_id=self.id)) is not None
        updated = []
        for tip in tips:
            is_funded = tip.amount <= (tip.paid_in_advance or 0)
            if tip.tippee_status == 'stub' or tip.tippee_goal == -1:
                is_funded |= has_donated_recently
            if tip.is_funded == is_funded:
                continue
            updated.append((cursor or self.db).one("""
                UPDATE tips
                   SET is_funded = %s
                 WHERE id = %s
             RETURNING *
            """, (is_funded, tip.id)))

        # Update giving on participant
        giving = (cursor or self.db).one("""
            UPDATE participants p
               SET giving = coalesce_currency_amount((
                     SELECT sum(t.amount, p.main_currency)
                       FROM current_tips t
                       JOIN participants tippee_p ON tippee_p.id = t.tippee
                      WHERE t.tipper = %(id)s
                        AND t.is_funded
                        AND tippee_p.status = 'active'
                        AND (tippee_p.goal IS NULL OR tippee_p.goal >= 0)
                   ), p.main_currency)
             WHERE p.id = %(id)s
         RETURNING giving
        """, dict(id=self.id))
        self.set_attributes(giving=giving)

        return updated

    def update_receiving(self, cursor=None):
        with self.db.get_cursor(cursor) as c:
            if self.kind == 'group':
                c.run("LOCK TABLE takes IN EXCLUSIVE MODE")
            zero = Money.ZEROS[self.main_currency]
            r = c.one("""
                WITH our_tips AS (
                         SELECT tip.amount
                           FROM current_tips tip
                           JOIN participants tipper_p ON tipper_p.id = tip.tipper
                          WHERE tip.tippee = %(id)s
                            AND tip.is_funded
                            AND tipper_p.is_suspended IS NOT true
                     )
                UPDATE participants p
                   SET receiving = taking + coalesce_currency_amount(
                           (SELECT sum(amount, %(currency)s) FROM our_tips),
                           %(currency)s
                       )
                     , npatrons = COALESCE((SELECT count(*) FROM our_tips), 0)
                 WHERE p.id = %(id)s
             RETURNING receiving, npatrons
            """, dict(id=self.id, currency=self.main_currency, zero=zero))
            self.set_attributes(receiving=r.receiving, npatrons=r.npatrons)
            if self.kind == 'group':
                self.recompute_actual_takes(c)


    def set_tip_to(self, tippee, periodic_amount, period='weekly', renewal_mode=None,
                   visibility=None, update_schedule=True, update_tippee=True):
        """Given a Participant or username, and amount as str, returns a dict.

        We INSERT instead of UPDATE, so that we have history to explore. The
        COALESCE function returns the first of its arguments that is not NULL.
        The effect here is to stamp all tips with the timestamp of the first
        tip from this user to that. I believe this is used to determine the
        order of transfers during payday.

        Returns a `Tip` object.

        """
        assert self.status == 'active'  # sanity check

        if isinstance(tippee, AccountElsewhere):
            tippee = tippee.participant
        elif not isinstance(tippee, Participant):
            tippee, u = Participant.from_username(tippee), tippee
            if not tippee:
                raise NoTippee(u)

        if self.id == tippee.id:
            raise NoSelfTipping

        if periodic_amount == 0:
            return self.stop_tip_to(tippee, update_schedule=update_schedule)

        periodic_amount = periodic_amount.convert_if_currency_is_phased_out()
        amount = (periodic_amount * PERIOD_CONVERSION_RATES[period]).round_down()

        if periodic_amount != 0:
            limits = DONATION_LIMITS[periodic_amount.currency][period]
            if periodic_amount < limits[0] or periodic_amount > limits[1]:
                raise BadAmount(periodic_amount, period, limits)
            if amount.currency not in tippee.accepted_currencies_set:
                raise BadDonationCurrency(tippee, amount.currency)
            if visibility and not tippee.accepts_tip_visibility(visibility):
                raise UnacceptedDonationVisibility(tippee, visibility)

        # Insert tip
        t = self.db.one("""\

            WITH current_tip AS (
                     SELECT *
                       FROM current_tips
                      WHERE tipper=%(tipper)s
                        AND tippee=%(tippee)s
                 )
            INSERT INTO tips
                        ( ctime, tipper, tippee, amount, period, periodic_amount
                        , paid_in_advance
                        , renewal_mode
                        , visibility )
                 VALUES ( COALESCE((SELECT ctime FROM current_tip), CURRENT_TIMESTAMP)
                        , %(tipper)s, %(tippee)s, %(amount)s, %(period)s, %(periodic_amount)s
                        , (SELECT convert(paid_in_advance, %(currency)s) FROM current_tip)
                        , coalesce(
                              %(renewal_mode)s,
                              (SELECT renewal_mode FROM current_tip WHERE renewal_mode > 0),
                              1
                          )
                        , coalesce(
                              %(visibility)s,
                              (SELECT abs(visibility) FROM current_tip),
                              1
                          ) )
              RETURNING tips

        """, dict(
            tipper=self.id, tippee=tippee.id, amount=amount, currency=amount.currency,
            period=period, periodic_amount=periodic_amount, renewal_mode=renewal_mode,
            visibility=visibility,
        ))
        t.tipper_p = self
        t.tippee_p = tippee

        # Update giving amount of tipper
        updated = self.update_giving()
        for u in updated:
            if u.id == t.id:
                t.set_attributes(is_funded=u.is_funded)
        if update_schedule:
            self.schedule_renewals()
        if update_tippee and t.is_funded:
            # Update receiving amount of tippee
            tippee.update_receiving()

        return t


    @staticmethod
    def _zero_tip(tippee, currency=None):
        if not isinstance(tippee, Participant):
            tippee = Participant.from_id(tippee)
        if currency is i18n.DEFAULT_CURRENCY or currency not in tippee.accepted_currencies_set:
            currency = tippee.main_currency
        zero = Money.ZEROS[currency]
        return Tip(
            amount=zero, is_funded=False, tippee=tippee.id, tippee_p=tippee,
            period='weekly', periodic_amount=zero, renewal_mode=0,
            visibility=0,
        )


    def stop_tip_to(self, tippee, update_schedule=True):
        t = self.db.one("""
            INSERT INTO tips
                      ( ctime, tipper, tippee, amount, period, periodic_amount
                      , paid_in_advance, is_funded, renewal_mode, visibility )
                 SELECT ctime, tipper, tippee, amount, period, periodic_amount
                      , paid_in_advance, is_funded, 0, visibility
                   FROM current_tips
                  WHERE tipper = %(tipper)s
                    AND tippee = %(tippee)s
                    AND renewal_mode > 0
              RETURNING tips
        """, dict(tipper=self.id, tippee=tippee.id))
        if not t:
            return
        if t.amount > (t.paid_in_advance or 0):
            # Update giving amount of tipper
            self.update_giving()
            # Update receiving amount of tippee
            tippee.update_receiving()
        if update_schedule:
            self.schedule_renewals()
        return t


    def hide_tip_to(self, tippee_id, hide=True):
        """Mark a donation as "hidden".
        """
        return self.db.one("""
            INSERT INTO tips
                      ( ctime, tipper, tippee, amount, period, periodic_amount
                      , paid_in_advance, is_funded, renewal_mode, visibility )
                 SELECT ctime, tipper, tippee, amount, period, periodic_amount
                      , paid_in_advance, is_funded, renewal_mode, -visibility
                   FROM current_tips
                  WHERE tipper = %(tipper)s
                    AND tippee = %(tippee)s
                    AND renewal_mode = 0
                    AND (visibility < 0) IS NOT %(hide)s
              RETURNING tips
        """, dict(tipper=self.id, tippee=tippee_id, hide=hide))


    def accepts_tip_visibility(self, visibility):
        bit = 2 ** (visibility - 1)
        acceptable_visibilites = self.recipient_settings.patron_visibilities or 1
        if self.payment_providers == 2:
            acceptable_visibilites &= 6
            acceptable_visibilites |= 2
        return acceptable_visibilites & bit > 0


    @cached_property
    def donor_category(self):
        if self.is_suspended is False:
            return 'trusted_donor'
        has_at_least_one_good_payment = self.db.one("""
            SELECT count(*)
              FROM payins
             WHERE payer = %s
               AND status = 'succeeded'
               AND refunded_amount IS NULL
               AND ctime < (current_timestamp - interval '30 days')
        """, (self.id,)) > 0
        if has_at_least_one_good_payment:
            return 'active_donor'
        else:
            return 'new_donor'


    def guess_payin_amount_maximum(self, cursor=None):
        """Return the maximum sum ever paid (manually) within a week.

        The query is limited to 50 payins in order to curtail its running time.
        """
        return (cursor or self.db).one("""
            WITH relevant_payins AS (
                SELECT pi.*
                  FROM payins pi
                 WHERE pi.payer = %(payer)s
                   AND pi.status IN ('pending', 'succeeded')
                   AND ( NOT pi.off_session OR (
                           SELECT sp.customized
                             FROM scheduled_payins sp
                            WHERE sp.payin = pi.id
                       ) )
              ORDER BY pi.ctime DESC
                 LIMIT 50
            )
            SELECT max(sums.amount)
              FROM ( SELECT sum(pi.amount, %(main_currency)s) OVER (
                                ORDER BY pi.ctime DESC
                                RANGE '1 week' PRECEDING
                            ) AS amount
                       FROM relevant_payins pi
                   ) sums
        """, dict(payer=self.id, main_currency=self.main_currency))


    def schedule_renewals(self, save=True, new_dates={}, new_amounts={}):
        """(Re)schedule this donor's future payments.
        """

        def get_tippees_tuple(sp):
            return tuple(sorted([tr['tippee_id'] for tr in sp.transfers]))

        def has_scheduled_payment_changed(cur, new):
            for k, v in new.__dict__.items():
                if getattr(cur, k) != v:
                    return True
            return False

        def find_partial_match(new_sp, current_schedule_map):
            """Try to find the scheduled payment that most closely resembles `new_sp`.
            """
            new_tippees_set = set(tr['tippee_id'] for tr in new_sp.transfers)
            best_match, best_match_score = None, 0
            for tr in new_sp.transfers:
                cur_sp = current_schedule_by_tippee.get(tr['tippee_id'])
                if not cur_sp:
                    continue
                cur_tippees = get_tippees_tuple(cur_sp)
                if cur_tippees not in current_schedule_map:
                    # This scheduled payin has already been matched to another one.
                    continue
                cur_tippees_set = set(cur_tippees)
                n_common_tippees = len(cur_tippees_set & new_tippees_set)
                if n_common_tippees > best_match_score:
                    best_match, best_match_score = cur_sp, n_common_tippees
            return best_match

        with self.db.get_cursor() as cursor:
            # Prevent race conditions
            if save:
                cursor.run("SELECT * FROM participants WHERE id = %s FOR UPDATE",
                           (self.id,))

            # Get renewable tips
            next_payday = compute_next_payday_date()
            renewable_tips = cursor.all("""
                SELECT t.*::tips, tippee_p, last_pt::payin_transfers
                  FROM current_tips t
                  JOIN participants tippee_p ON tippee_p.id = t.tippee
             LEFT JOIN LATERAL (
                           SELECT pt.*
                             FROM payin_transfers pt
                            WHERE pt.payer = t.tipper
                              AND coalesce(pt.team, pt.recipient) = t.tippee
                         ORDER BY pt.ctime DESC
                            LIMIT 1
                       ) last_pt ON true
                 WHERE t.tipper = %s
                   AND t.renewal_mode > 0
                   AND t.paid_in_advance IS NOT NULL
                   AND tippee_p.status = 'active'
                   AND ( tippee_p.goal IS NULL OR tippee_p.goal >= 0 )
                   AND tippee_p.is_suspended IS NOT TRUE
                   AND tippee_p.payment_providers > 0
              ORDER BY t.tippee
            """, (self.id,))
            for tip, tippee_p, last_pt in renewable_tips:
                tip.tippee_p = tippee_p
                tip.periodic_amount = tip.periodic_amount.convert_if_currency_is_phased_out()
                tip.amount = tip.amount.convert_if_currency_is_phased_out()
                tip.paid_in_advance = tip.paid_in_advance.convert_if_currency_is_phased_out()
                tip.due_date = tip.compute_renewal_due_date(next_payday, cursor)
            renewable_tips = [
                tip for tip, tippee_p, last_pt in renewable_tips
                if last_pt.id is None or
                   last_pt.status == 'succeeded' or
                   last_pt.status == 'failed' and
                   last_pt.ctime.date() < (tip.due_date - timedelta(weeks=1)) and
                   tip.due_date >= date(2024, 9, 4)
            ]

            # Get the existing schedule
            current_schedule = cursor.all("""
                SELECT sp.*
                  FROM scheduled_payins sp
                 WHERE sp.payer = %s
                   AND sp.payin IS NULL
              ORDER BY sp.execution_date, sp.id
            """, (self.id,))
            current_schedule_map = {get_tippees_tuple(sp): sp for sp in current_schedule}
            current_schedule_by_tippee = {}
            for sp in current_schedule:
                for tr in sp.transfers:
                    if isinstance(tr['amount'], dict):
                        tr['amount'] = Money(**tr['amount'])
                    if tr['tippee_id'] in current_schedule_by_tippee:
                        # This isn't supposed to happen.
                        continue
                    current_schedule_by_tippee[tr['tippee_id']] = sp

            # Gather some data on past payments
            if renewable_tips:
                tippees = set(t.tippee for t in renewable_tips)
                # For each renewable tip, compute the renewal amount, using the
                # amount of the last *manual* payment. (If we based renewal
                # amounts on previous renewal amounts, then past mistakes in the
                # computation would be repeated forever.)
                last_manual_payment_amounts = dict(cursor.all("""
                    SELECT tippee, round(
                               ( SELECT sum(pt.amount, payin_amount::currency) FILTER (
                                            WHERE coalesce(pt.team, pt.recipient) = tippee
                                        ) /
                                        sum(pt.amount, payin_amount::currency)
                                   FROM payin_transfers pt
                                  WHERE pt.payin = payin_id
                                    AND pt.status = 'succeeded'
                               ) * (
                                   payin_amount - coalesce_currency_amount(
                                       payin_refunded_amount, payin_amount::currency
                                   )
                               )
                           ) AS amount
                      FROM ( SELECT DISTINCT ON (coalesce(pt.team, pt.recipient))
                                    coalesce(pt.team, pt.recipient) AS tippee,
                                    pi.id AS payin_id,
                                    pi.amount AS payin_amount,
                                    pi.refunded_amount AS payin_refunded_amount
                               FROM payin_transfers pt
                               JOIN payins pi ON pi.id = pt.payin
                              WHERE pt.payer = %(payer)s
                                AND coalesce(pt.team, pt.recipient) IN %(tippees)s
                                AND pt.status = 'succeeded'
                                AND ( NOT pi.off_session OR (
                                        SELECT sp.customized
                                          FROM scheduled_payins sp
                                         WHERE sp.payin = pi.id
                                    ) )
                           ORDER BY coalesce(pt.team, pt.recipient)
                                  , pt.ctime DESC
                           ) x
                """, dict(payer=self.id, tippees=tippees)))
                for tip in renewable_tips:
                    if tip.renewal_mode == 2:
                        if tip.tippee_p.payment_providers & 1 == 0:
                            # Automatic payments are only possible through Stripe.
                            tip.renewal_mode = 1
                        elif tip.amount.currency not in tip.tippee_p.accepted_currencies_set:
                            # This tip needs to be modified because the recipient
                            # no longer accepts that currency.
                            tip.renewal_mode = 1
                    if tip.renewal_mode == 2:
                        last_payment_amount = last_manual_payment_amounts.get(tip.tippee)
                        if last_payment_amount:
                            tip.renewal_amount = last_payment_amount.convert(tip.amount.currency)
                        else:
                            tip.renewal_amount = None
                        if not tip.renewal_amount or tip.renewal_amount < tip.amount:
                            pp = PayinProspect(self, [tip], 'stripe')
                            tip.renewal_amount = pp.moderate_proposed_amount
                        del last_payment_amount
                    else:
                        tip.renewal_amount = None
                del last_manual_payment_amounts
                # For each renewable tip, fetch the amount of the last payment.
                # This is used further down to ensure that a renewal isn't
                # scheduled too early.
                last_payment_amounts = dict(cursor.all("""
                    SELECT DISTINCT ON (coalesce(pt.team, pt.recipient))
                           coalesce(pt.team, pt.recipient) AS tippee,
                           pt.amount
                      FROM payin_transfers pt
                     WHERE pt.payer = %(payer)s
                       AND coalesce(pt.team, pt.recipient) IN %(tippees)s
                       AND pt.status = 'succeeded'
                  ORDER BY coalesce(pt.team, pt.recipient)
                         , pt.ctime DESC
                """, dict(payer=self.id, tippees=tippees)))
                del tippees
                # Try to guess how much the donor is willing to pay within a
                # week by looking at past (manual) payments.
                past_payin_amount_maximum = self.guess_payin_amount_maximum(cursor)

            # Group the tips into payments
            # 1) Group the tips by renewal_mode and currency.
            naive_tip_groups = defaultdict(list)
            for tip in renewable_tips:
                naive_tip_groups[(tip.renewal_mode, tip.amount.currency)].append(tip)
            del renewable_tips
            # 2) Subgroup by payment processor and geography.
            for key, tips in naive_tip_groups.items():
                groups = self.group_tips_into_payments(tips)[0]
                for tip in groups['currency_conflict']:
                    groups['fundable'].append([tip])
                naive_tip_groups[key] = groups['fundable']
            # 3) Subgroup based on when the renewal is due and how much was paid last time.
            tip_groups = []
            due_date_getter = attrgetter('due_date')
            for (renewal_mode, tips_currency), naive_groups in naive_tip_groups.items():
                for naive_group in naive_groups:
                    naive_group.sort(key=due_date_getter)
                    group = None
                    execution_date = weeks_until_execution = None  # for the linter
                    for tip in naive_group:
                        last_payment_amount = last_payment_amounts.get(tip.tippee)
                        # Start a new group if…
                        start_new_group = (
                            # there isn't a group yet; or
                            group is None or
                            # the due date is at least 6 months further into the future; or
                            tip.due_date >= (execution_date + timedelta(weeks=26)) or
                            # the due date is at least 1 week further into the future, and
                            tip.due_date >= (execution_date + timedelta(weeks=1)) and
                            # the advance will still be more than half of the last payment
                            last_payment_amount is not None and
                            (tip.paid_in_advance - tip.amount * weeks_until_execution) /
                            last_payment_amount.convert(tips_currency) >
                            Decimal('0.5')
                        )
                        if start_new_group:
                            group = [tip]
                            tip_groups.append((renewal_mode, tips_currency, group))
                            execution_date = tip.due_date
                            weeks_until_execution = (execution_date - next_payday).days // 7
                        else:
                            group.append(tip)
                    del group, last_payment_amount, naive_group, weeks_until_execution
                del naive_groups
            del naive_tip_groups

            # Compile the new schedule and compare it to the old one
            tippee_id_getter = itemgetter('tippee_id')
            min_automatic_debit_date = date(2020, 2, 14)
            new_schedule = []
            insertions, updates, deletions, unchanged = [], [], [], []
            for renewal_mode, payin_currency, payin_tips in tip_groups:
                execution_date = payin_tips[0].due_date
                if renewal_mode == 2:
                    # We schedule automatic renewals one day early so that the
                    # donor has a little bit of time to react if it fails.
                    execution_date -= timedelta(days=1)
                    execution_date = max(execution_date, min_automatic_debit_date)
                new_sp = Object(
                    amount=Money.sum(
                        (t.renewal_amount for t in payin_tips),
                        payin_currency
                    ) if renewal_mode == 2 else None,
                    transfers=[
                        {
                            'tippee_id': tip.tippee,
                            'tippee_username': tip.tippee_p.username,
                            'amount': tip.renewal_amount,
                        } for tip in payin_tips
                    ],
                    execution_date=execution_date,
                    automatic=(renewal_mode == 2),
                )
                new_sp.transfers.sort(key=tippee_id_getter)
                # Check the charge amount
                if renewal_mode == 2:
                    unadjusted_amount = new_sp.amount
                    pp = PayinProspect(self, payin_tips, 'stripe')
                    if new_sp.amount < pp.min_acceptable_amount:
                        new_sp.amount = pp.min_acceptable_amount
                    elif new_sp.amount > pp.max_acceptable_amount:
                        new_sp.amount = pp.max_acceptable_amount
                    if past_payin_amount_maximum:
                        maximum = past_payin_amount_maximum.convert(payin_currency)
                        if new_sp.amount > maximum:
                            new_sp.amount = max(
                                maximum,
                                pp.moderate_fee_amount,
                                pp.one_weeks_worth,
                            )
                    if new_sp.amount != unadjusted_amount:
                        tr_amounts = resolve_amounts(
                            new_sp.amount,
                            {tip.tippee: tip.amount for tip in payin_tips}
                        )
                        for tr in new_sp.transfers:
                            tr['amount'] = tr_amounts[tr['tippee_id']]
                        del tr_amounts
                    del unadjusted_amount
                # Try to find this new payment in the current schedule
                tippees = get_tippees_tuple(new_sp)
                cur_sp = current_schedule_map.pop(tippees, None)
                if cur_sp:
                    # Found it, now we check if the two are different
                    if cur_sp.customized:
                        # Don't modify a payment that has been explicitly
                        # customized by the donor.
                        new_sp.execution_date = cur_sp.execution_date
                        if new_sp.automatic and cur_sp.automatic:
                            new_sp.amount = cur_sp.amount
                            new_sp.transfers = cur_sp.transfers
                        if new_sp.amount and new_sp.amount.currency != payin_currency:
                            # … unless the currency has changed.
                            new_sp.amount = new_sp.amount.convert(payin_currency)
                            new_sp.transfers = [
                                dict(tr, amount=tr['amount'].convert(payin_currency))
                                for tr in new_sp.transfers
                            ]
                        new_sp.customized = True
                    else:
                        preserve_the_execution_date = (
                            # Don't change the execution date if the payment was
                            # scheduled late.
                            new_sp.execution_date < (
                                cur_sp.ctime.date() + timedelta(weeks=1)
                            ) or
                            # Don't push back a payment by only a few weeks
                            # if we've already notified the payer.
                            cur_sp.notifs_count and
                            new_sp.amount == cur_sp.amount and
                            new_sp.execution_date <= (
                                cur_sp.execution_date + timedelta(weeks=4)
                            )
                        )
                        if preserve_the_execution_date:
                            new_sp.execution_date = cur_sp.execution_date
                    if cur_sp.id in new_dates or cur_sp.id in new_amounts:
                        new_sp.customized = cur_sp.customized
                        new_date = new_dates.get(cur_sp.id)
                        if new_date and new_sp.execution_date != new_date:
                            new_sp.execution_date = new_date
                            new_sp.customized = True
                        new_amount = new_amounts.get(cur_sp.id) if new_sp.automatic else None
                        if new_amount and new_sp.amount != new_amount:
                            if new_amount.currency != payin_currency:
                                raise UnexpectedCurrency(new_amount, payin_currency)
                            new_sp.amount = new_amount
                            tr_amounts = resolve_amounts(new_amount, {
                                tr['tippee_id']: tr['amount'].convert(payin_currency)
                                for tr in new_sp.transfers
                            })
                            for tr in new_sp.transfers:
                                tr['amount'] = tr_amounts[tr['tippee_id']]
                            new_sp.customized = True
                    if has_scheduled_payment_changed(cur_sp, new_sp):
                        updates.append((cur_sp, new_sp))
                    else:
                        unchanged.append(cur_sp)
                else:
                    # No exact match, so we look for a partial match
                    cur_sp = find_partial_match(new_sp, current_schedule_map)
                    if cur_sp:
                        # Found a partial match
                        current_schedule_map.pop(get_tippees_tuple(cur_sp))
                        updates.append((cur_sp, new_sp))
                    else:
                        # No match, this is a completely new payment
                        insertions.append(new_sp)
                new_schedule.append(new_sp)
            deletions = list(current_schedule_map.values())
            del current_schedule_map

            # Make sure any newly scheduled automatic payment is at least a week away
            today = utcnow().date()
            one_week_from_today = today + timedelta(weeks=1)
            for new_sp in insertions:
                if new_sp.automatic:
                    if new_sp.execution_date < one_week_from_today:
                        new_sp.execution_date = one_week_from_today
            for cur_sp, new_sp in updates:
                if new_sp.automatic and not cur_sp.automatic:
                    if new_sp.execution_date < one_week_from_today:
                        new_sp.execution_date = one_week_from_today

            # Upsert the new schedule
            notify = False
            if save and (insertions or updates or deletions):
                # Delete, insert and update the scheduled payins
                execute_batch(cursor, """
                    DELETE FROM scheduled_payins WHERE id = %s
                """, [(sp.id,) for sp in deletions])
                new_ids = execute_values(cursor, """
                    INSERT INTO scheduled_payins
                                (execution_date, payer, amount, transfers, automatic, customized)
                         VALUES %s
                      RETURNING id
                """, [
                    (sp.execution_date, self.id, sp.amount, json.dumps(sp.transfers),
                     sp.automatic, getattr(sp, 'customized', None))
                    for sp in insertions
                ], fetch=True)
                for i, row in enumerate(new_ids):
                    insertions[i].id = row.id
                three_weeks_from_today = today + timedelta(days=21)
                for cur_sp, new_sp in updates:
                    new_sp.id = cur_sp.id
                    reset_notifs = (
                        new_sp.automatic and not cur_sp.automatic or
                        new_sp.execution_date > cur_sp.execution_date and
                        new_sp.execution_date >= three_weeks_from_today
                    )
                    if reset_notifs:
                        new_sp.notifs_count = 0
                        new_sp.last_notif_ts = None
                    else:
                        new_sp.notifs_count = cur_sp.notifs_count
                        new_sp.last_notif_ts = cur_sp.last_notif_ts
                execute_batch(cursor, """
                    UPDATE scheduled_payins
                       SET amount = %s
                         , transfers = %s
                         , execution_date = %s
                         , automatic = %s
                         , customized = %s
                         , notifs_count = %s
                         , last_notif_ts = %s
                         , mtime = current_timestamp
                     WHERE id = %s
                """, [
                    (new_sp.amount,
                     json.dumps(new_sp.transfers),
                     new_sp.execution_date,
                     new_sp.automatic,
                     getattr(new_sp, 'customized', None),
                     new_sp.notifs_count,
                     new_sp.last_notif_ts,
                     cur_sp.id)
                    for cur_sp, new_sp in updates
                ])
                # Determine if we need to notify the user
                notify = (
                    any(sp.notifs_count for sp in deletions) or
                    any(
                        old_sp.notifs_count and (
                            new_sp.amount != old_sp.amount or
                            new_sp.execution_date != old_sp.execution_date or
                            new_sp.automatic != old_sp.automatic
                        )
                        for old_sp, new_sp in updates
                    )
                )
        new_schedule.sort(key=lambda sp: (sp.execution_date, getattr(sp, 'id', id(sp))))

        # Notify the donor of important changes in scheduled payments
        if notify:
            sp_to_dict = lambda sp: {
                'amount': sp.amount,
                'execution_date': sp.execution_date,
            }
            self.notify(
                'payment_schedule_modified',
                force_email=True,
                added_payments=[sp_to_dict(new_sp) for new_sp in insertions],
                cancelled_payments=[sp_to_dict(old_sp) for old_sp in deletions],
                modified_payments=[t for t in (
                    (sp_to_dict(old_sp), sp_to_dict(new_sp))
                    for old_sp, new_sp in updates
                    if old_sp.notifs_count > 0
                ) if t[0] != t[1]],
                new_schedule=new_schedule,
            )

        return new_schedule


    def get_tip_to(self, tippee, currency=None):
        """Given a participant (or their id), returns an `Object`.
        """
        if not isinstance(tippee, Participant):
            tippee = Participant.from_id(tippee)
        r = self.db.one("""\
            SELECT tips
              FROM tips
             WHERE tipper=%s
               AND tippee=%s
          ORDER BY mtime DESC
             LIMIT 1
        """, (self.id, tippee.id))
        if r:
            return r
        return self._zero_tip(tippee, self.main_currency)


    def get_tip_distribution(self):
        """
            Returns a data structure in the form of::

                [
                    [TIPAMOUNT1, TIPAMOUNT2...TIPAMOUNTN],
                    total_number_patrons_giving_to_me,
                    total_amount_received
                ]

            where each TIPAMOUNTN is in the form::

                [
                    amount,
                    number_of_tippers_for_this_amount,
                    total_amount_given_at_this_amount,
                    total_amount_given_at_this_amount_converted_to_reference_currency,
                    proportion_of_tips_at_this_amount,
                    proportion_of_total_amount_at_this_amount
                ]

        """
        recs = self.db.all("""
            SELECT amount
                 , count(amount) AS ncontributing
              FROM ( SELECT DISTINCT ON (tipper)
                            amount
                          , tipper
                          , is_funded
                       FROM tips
                      WHERE tippee=%s
                   ORDER BY tipper
                          , mtime DESC
                    ) AS foo
             WHERE is_funded
          GROUP BY amount
          ORDER BY (amount).amount
        """, (self.id,))
        tip_amounts = []
        npatrons = 0
        currency = self.main_currency
        contributed = Money.ZEROS[currency]
        for rec in recs:
            tip_amounts.append([
                rec.amount,
                rec.ncontributing,
                rec.amount * rec.ncontributing,
            ])
            tip_amounts[-1].append(tip_amounts[-1][2].convert(currency))
            contributed += tip_amounts[-1][3]
            npatrons += rec.ncontributing

        for row in tip_amounts:
            row.append((row[1] / npatrons) if npatrons > 0 else 0)
            row.append((row[3] / contributed) if contributed > 0 else 0)

        return tip_amounts, npatrons, contributed


    def get_giving_details(self):
        """Get details of current outgoing donations and pledges.
        """

        tips = self.db.all("""\

                SELECT amount
                     , period
                     , periodic_amount
                     , tippee
                     , t.ctime
                     , t.mtime
                     , p AS tippee_p
                     , t.is_funded
                     , t.paid_in_advance
                     , t.renewal_mode
                     , t.visibility
                     , p.payment_providers
                  FROM current_tips t
                  JOIN participants p ON p.id = t.tippee
                 WHERE t.tipper = %s
                   AND p.status <> 'stub'
                   AND t.visibility > 0
              ORDER BY tippee, t.mtime DESC

        """, (self.id,))

        pledges = self.db.all("""\

                SELECT amount
                     , period
                     , periodic_amount
                     , tippee
                     , t.ctime
                     , t.mtime
                     , t.renewal_mode
                     , t.visibility
                     , (e, p)::elsewhere_with_participant AS e_account
                  FROM current_tips t
                  JOIN participants p ON p.id = t.tippee
                  JOIN elsewhere e ON e.participant = t.tippee
                 WHERE t.tipper = %s
                   AND p.status = 'stub'
                   AND t.visibility > 0
              ORDER BY tippee, t.mtime DESC

        """, (self.id,))

        return tips, pledges

    def get_tips_awaiting_payment(self, weeks_early=3, exclude_recipients_of=None):
        """Fetch a list of the user's donations that need to be renewed, and
        determine if some of them can be grouped into a single charge.

        Stripe is working on lifting the "same region" limitation of one-to-many
        payments, so eventually we'll be able to group all Stripe payments.

        Returns a dict of the donations grouped by status:

        - 'fundable': renewable donations grouped into lists (one per payment)
        - 'no_provider': the tippee hasn't connected any payment account
        - 'no_taker': there is no team member willing and able to receive the donation
        - 'self_donation': the donor is the only fundable member of the tippee's team
        - 'suspended': the tippee's account is suspended

        """
        params = dict(tipper_id=self.id, weeks_early=weeks_early)
        if exclude_recipients_of:
            exclude = """
               AND t.tippee NOT IN (
                       SELECT coalesce(pt.team, pt.recipient)
                         FROM payin_transfers pt
                        WHERE pt.payin = %(payin_id)s
                   )
            """
            params['payin_id'] = exclude_recipients_of.id
        else:
            exclude = ""
        tips = self.db.all("""
            SELECT t.*, p AS tippee_p
              FROM current_tips t
              JOIN participants p ON p.id = t.tippee
         LEFT JOIN scheduled_payins sp ON sp.payer = t.tipper
                                      AND sp.payin IS NULL
                                      AND t.tippee::text IN (
                                              SELECT tr->>'tippee_id'
                                                FROM json_array_elements(sp.transfers) tr
                                          )
             WHERE t.tipper = %(tipper_id)s
               AND t.renewal_mode > 0
               AND ( t.paid_in_advance IS NULL OR
                     t.paid_in_advance < (t.amount * %(weeks_early)s) OR
                     sp.execution_date <= (current_date + interval '%(weeks_early)s weeks')
                   )
               AND p.status = 'active'
               AND ( p.goal IS NULL OR p.goal >= 0 )
               AND NOT EXISTS (
                       SELECT 1
                         FROM payin_transfers pt
                         JOIN payins pi ON pi.id = pt.payin
                         JOIN exchange_routes r ON r.id = pi.route
                        WHERE pt.payer = t.tipper
                          AND COALESCE(pt.team, pt.recipient) = t.tippee
                          AND ( pi.status IN ('awaiting_review', 'pending') OR
                                pt.status IN ('awaiting_review', 'pending') OR
                                pi.status = 'succeeded' AND
                                pi.ctime > (current_timestamp - interval '5 days') )
                        LIMIT 1
                   ){}
          ORDER BY ( SELECT 1
                       FROM current_takes take
                      WHERE take.team = t.tippee
                        AND take.member = t.tipper
                   ) NULLS FIRST
                 , (t.paid_in_advance).amount / (t.amount).amount NULLS FIRST
                 , t.ctime
        """.format(exclude), params)
        return self.group_tips_into_payments(tips)

    def group_tips_into_payments(self, tips):
        groups = dict(
            currency_conflict=[], fundable=[], no_provider=[], no_taker=[],
            self_donation=[], suspended=[],
        )
        n_fundable = 0
        stripe_europe = {}
        for tip in tips:
            tippee_p = tip.tippee_p
            if tippee_p.payment_providers == 0:
                groups['no_provider'].append(tip)
            elif tippee_p.is_suspended:
                groups['suspended'].append(tip)
            elif tip.amount.currency not in tippee_p.accepted_currencies_set:
                n_fundable += 1
                groups['currency_conflict'].append(tip)
            elif tippee_p.kind == 'group':
                members = self.db.all("""
                    SELECT t.member
                      FROM current_takes t
                      JOIN participants p ON p.id = t.member
                     WHERE t.team = %s
                       AND t.amount <> 0
                       AND p.payment_providers > 0
                       AND p.is_suspended IS NOT TRUE
                  ORDER BY t.member <> %s DESC
                """, (tippee_p.id, self.id))
                if not members:
                    groups['no_taker'].append(tip)
                elif len(members) == 1 and members[0] == self.id:
                    groups['self_donation'].append(tip)
                else:
                    n_fundable += 1
                    in_sepa = tip.tippee_p.has_stripe_sepa_for(self)
                    if in_sepa:
                        group = stripe_europe.setdefault(tip.amount.currency, [])
                        if len(group) == 0:
                            groups['fundable'].append(group)
                        group.append(tip)
                    else:
                        groups['fundable'].append([tip])
            else:
                n_fundable += 1
                in_sepa = tip.tippee_p.has_stripe_sepa_for(self)
                if in_sepa:
                    group = stripe_europe.setdefault(tip.amount.currency, [])
                    if len(group) == 0:
                        groups['fundable'].append(group)
                    group.append(tip)
                else:
                    groups['fundable'].append([tip])
        return groups, n_fundable

    def has_stripe_sepa_for(self, tipper):
        if tipper == self or self.payment_providers & 1 == 0:
            return False
        if self.kind == 'group':
            return self.db.one("""
                SELECT true
                  FROM current_takes t
                  JOIN participants p ON p.id = t.member
                  JOIN payment_accounts a ON a.participant = t.member
                 WHERE t.team = %(tippee)s
                   AND t.member <> %(tipper)s
                   AND t.amount <> 0
                   AND p.is_suspended IS NOT TRUE
                   AND a.provider = 'stripe'
                   AND a.is_current
                   AND a.charges_enabled
                   AND a.country IN %(SEPA)s
                 LIMIT 1
            """, dict(tipper=tipper.id, tippee=self.id, SEPA=SEPA))
        else:
            return self.db.one("""
                SELECT true
                  FROM payment_accounts a
                 WHERE a.participant = %(tippee)s
                   AND a.provider = 'stripe'
                   AND a.is_current
                   AND a.charges_enabled
                   AND a.country IN %(SEPA)s
                 LIMIT 1
            """, dict(tippee=self.id, SEPA=SEPA))

    def get_tips_to(self, tippee_ids):
        return self.db.all("""
            SELECT t.*, p AS tippee_p
              FROM current_tips t
              JOIN participants p ON p.id = t.tippee
             WHERE t.tipper = %s
               AND t.tippee IN %s
        """, (self.id, tuple(tippee_ids)))

    def get_tips_receiving(self):
        return self.db.all("""
            SELECT *
              FROM current_tips
             WHERE tippee=%s
               AND amount>0
        """, (self.id,))


    def get_age_in_seconds(self):
        if self.join_time is not None:
            return (utcnow() - self.join_time).total_seconds()
        return -1


    # Identity (v2)
    # =============

    def get_current_identity(self):
        encrypted = self.db.one("""
            SELECT info
              FROM identities
             WHERE participant = %s
          ORDER BY ctime DESC
             LIMIT 1
        """, (self.id,))
        if encrypted is None:
            return None
        return encrypted.decrypt()

    def insert_identity(self, info):
        self.db.run("""
            INSERT INTO identities
                        (participant, info)
                 VALUES (%s, %s)
        """, (self.id, website.cryptograph.encrypt_dict(info)))


    # Accounts Elsewhere
    # ==================

    def get_accounts_elsewhere(self, platform=None, is_team=None, url_required=False):
        """Return a sorted list of AccountElsewhere instances.
        """
        accounts = self.db.all("""

            SELECT (e, p)::elsewhere_with_participant
              FROM elsewhere e
              JOIN participants p ON p.id = e.participant
             WHERE e.participant = %s
               AND coalesce(e.platform = %s, true)
               AND coalesce(e.is_team = %s, true)

        """, (self.id, platform, is_team))
        accounts.sort(key=lambda a: (website.platforms[a.platform].rank, a.is_team, a.user_id))
        if url_required:
            accounts = [a for a in accounts if a.platform_data.account_url and a.missing_since is None]
        return accounts

    def take_over(self, account, have_confirmation=False):
        """Given an AccountElsewhere or a tuple (platform_name, domain, user_id),
        associate an elsewhere account.

        Returns None or raises NeedConfirmation.

        This method associates an account on another platform (GitHub, Twitter,
        etc.) with the given Liberapay participant. Every account elsewhere has an
        associated Liberapay participant account, even if its only a stub
        participant (it allows us to track pledges to that account should they
        ever decide to join Liberapay).

        In certain circumstances, we want to present the user with a
        confirmation before proceeding to transfer the account elsewhere to
        the new Liberapay account; NeedConfirmation is the signal to request
        confirmation.
        """

        if isinstance(account, AccountElsewhere):
            platform, domain, user_id = account.platform, account.domain, account.user_id
            assert user_id, f"user_id is {user_id!r}"
        else:
            assert account[2], f"user_id is {account[2]!r}"
            platform, domain, user_id = map(str, account)

        CREATE_TEMP_TABLE_FOR_TIPS = """
            CREATE TEMP TABLE temp_tips ON COMMIT drop AS
                SELECT *
                  FROM current_tips
                 WHERE (tippee = %(dead)s OR tippee = %(live)s)
                   AND renewal_mode > 0;
        """

        CONSOLIDATE_TIPS_RECEIVING = """
            -- Create a new set of tips, one for each current tip *to* either
            -- the dead or the live account. If a user was tipping both the
            -- dead and the live account, then we keep the highest tip. We don't
            -- sum the amounts to prevent the new one from being above the
            -- maximum allowed.
            INSERT INTO tips
                      ( ctime, tipper, tippee, amount, period
                      , periodic_amount, is_funded, renewal_mode, visibility
                      , paid_in_advance )
                 SELECT DISTINCT ON (tipper)
                        ctime, tipper, %(live)s AS tippee, amount, period
                      , periodic_amount, is_funded, renewal_mode, visibility
                      , ( SELECT sum(t2.paid_in_advance, t.amount::currency)
                            FROM temp_tips t2
                           WHERE t2.tipper = t.tipper
                        ) AS paid_in_advance
                   FROM temp_tips t
                  WHERE (tippee = %(dead)s OR tippee = %(live)s)
                        -- Include tips *to* either the dead or live account.
                AND NOT (tipper = %(dead)s OR tipper = %(live)s)
                        -- Don't include tips *from* the dead or live account,
                        -- lest we convert cross-tipping to self-tipping.
               ORDER BY tipper, amount DESC
        """

        ZERO_OUT_OLD_TIPS_RECEIVING = """
            INSERT INTO tips
                      ( ctime, tipper, tippee, amount, period, periodic_amount
                      , paid_in_advance, is_funded, renewal_mode, visibility )
                 SELECT ctime, tipper, tippee, amount, period, periodic_amount
                      , NULL, false, 0, -visibility
                   FROM temp_tips
                  WHERE tippee = %(dead)s
                    AND ( coalesce_currency_amount(paid_in_advance, amount::currency) > 0 OR
                          renewal_mode > 0 )
        """

        with self.db.get_cursor() as cursor:

            # Load the existing connection
            # Every account elsewhere has at least a stub participant account
            # on Liberapay.
            elsewhere = cursor.one("""
                SELECT (e, p)::elsewhere_with_participant
                  FROM elsewhere e
                  JOIN participants p ON p.id = e.participant
                 WHERE e.platform=%s AND e.domain=%s AND e.user_id=%s
            """, (platform, domain, user_id), default=Exception)
            other = elsewhere.participant

            if self.id == other.id:
                # this is a no op - trying to take over itself
                return

            # Save old tips so we can notify patrons that they've been claimed
            old_tips = other.get_tips_receiving() if other.status == 'stub' else None

            # Make sure we have user confirmation if the other participant is not
            # a stub; since we are taking the account elsewhere away from another
            # viable participant.
            other_is_a_real_participant = other.status != 'stub'
            if other_is_a_real_participant and not have_confirmation:
                raise NeedConfirmation()

            # Do the deal
            cursor.run("""
                UPDATE elsewhere
                   SET participant=%s
                 WHERE platform=%s
                   AND domain=%s
                   AND user_id=%s
            """, (self.id, platform, domain, user_id))

            # Turn pledges into actual tips
            if old_tips:
                params = dict(live=self.id, dead=other.id)
                cursor.run(CREATE_TEMP_TABLE_FOR_TIPS, params)
                cursor.run(CONSOLIDATE_TIPS_RECEIVING, params)
                cursor.run(ZERO_OUT_OLD_TIPS_RECEIVING, params)

            # Try to delete the stub account, or prevent new pledges to it
            if not other_is_a_real_participant:
                cursor.run("""
                    DO $$
                    BEGIN
                        DELETE FROM participants WHERE id = %(dead)s;
                    EXCEPTION WHEN OTHERS THEN
                        UPDATE participants
                           SET goal = (-1, main_currency)
                         WHERE id = %(dead)s;
                    END;
                    $$ LANGUAGE plpgsql;
                """, dict(dead=other.id))

            # Log the event
            self.add_event(cursor, 'take-over', dict(
                platform=platform, domain=domain, user_id=user_id, owner=other.id
            ))

        self.update_avatar()

        # Note: the order matters here, receiving needs to be updated before giving
        self.update_receiving()
        self.update_giving()

    def delete_elsewhere(self, platform, domain, user_id):
        user_id = str(user_id)
        with self.db.get_cursor() as c:
            c.one("""
                DELETE FROM elsewhere
                 WHERE participant=%s
                   AND platform=%s
                   AND domain=%s
                   AND user_id=%s
             RETURNING participant
            """, (self.id, platform, domain, user_id), default=NonexistingElsewhere)
            detached_repos_count = c.one("""
                WITH detached AS (
                         UPDATE repositories
                            SET participant = null
                          WHERE participant = %s
                            AND platform = %s
                            AND owner_id = %s
                      RETURNING id
                     )
                SELECT count(*) FROM detached
            """, (self.id, platform, user_id))
            self.add_event(c, 'delete_elsewhere', dict(
                platform=platform, domain=domain, user_id=user_id,
                detached_repos_count=detached_repos_count,
            ))
        self.update_avatar()


    # Repositories
    # ============

    def get_repos_for_profile(self):
        return self.db.all("""
            SELECT r
              FROM repositories r
             WHERE r.participant = %s
               AND r.show_on_profile
          ORDER BY r.is_fork ASC NULLS FIRST, r.last_update DESC
             LIMIT 20
        """, (self.id,))

    def get_repos_on_platform(self, platform, limit=50, offset=None, owner_id=None):
        return self.db.all("""
            SELECT r
              FROM repositories r
             WHERE r.participant = %s
               AND r.platform = %s
               AND coalesce(r.owner_id = %s, true)
          ORDER BY r.is_fork ASC NULLS FIRST, r.last_update DESC
             LIMIT %s
            OFFSET %s
        """, (self.id, platform, owner_id, limit, offset))


    # More Random Stuff
    # =================

    def to_dict(self, details=False):
        output = {
            'id': self.id,
            'username': self.username,
            'display_name': self.public_name,
            'avatar': self.avatar_url,
            'kind': self.kind,
        }

        if not details:
            return output

        # Key: npatrons
        output['npatrons'] = self.npatrons

        # Key: goal
        # Values:
        #   undefined - user is not here to receive tips, but will generally regift them
        #   null - user has no funding goal
        #   3.00 - user wishes to receive at least this amount
        if self.goal != 0:
            if self.goal and self.goal > 0:
                goal = self.goal
            else:
                goal = None
            output['goal'] = goal

        # Key: receiving
        # Values:
        #   null - user does not publish how much they receive
        #   3.00 - user receives this amount in tips
        if not self.hide_receiving:
            receiving = self.receiving
        else:
            receiving = None
        output['receiving'] = receiving

        # Key: giving
        # Values:
        #   null - user does not publish how much they give
        #   3.00 - user gives this amount in tips
        if not self.hide_giving:
            giving = self.giving
        else:
            giving = None
        output['giving'] = giving

        # Keys: summaries and statements
        # Values: lists of dicts containing the user's texts in various languages
        output['summaries'] = self.db.all("""
            SELECT lang, content
              FROM statements
             WHERE participant = %s
               AND type = 'summary'
        """, (self.id,), back_as=dict)
        output['statements'] = self.db.all("""
            SELECT lang, content
              FROM statements
             WHERE participant = %s
               AND type = 'profile'
        """, (self.id,), back_as=dict)

        return output

    def path(self, path, query=''):
        if query:
            assert '?' not in path
            if isinstance(query, dict):
                query = '?' + urlencode(query, doseq=True)
            else:
                assert query[0] == '?'
        return '/%s/%s%s' % (self.username, path, query)

    def link(self, path='', query=''):
        return HTML_A % (self.path(path, query), self.username)

    @property
    def is_person(self):
        return self.kind in ('individual', 'organization')

    def controls(self, other):
        return isinstance(other, Participant) and (
            self.id == other.id or
            other.kind == 'group' and self.member_of(other)
        )

    def update_bit(self, column, bit, on):
        """Updates one bit in an integer in the participants table.

        Bits are used for email notification preferences and privacy settings.
        """
        assert isinstance(getattr(self, column), int)  # anti sql injection
        assert column != 'privileges'  # protection against privilege escalation
        if on:
            mask = bit
            op = '|'
        else:
            mask = 2147483647 ^ bit
            op = '&'
        r = self.db.one("""
            UPDATE participants
               SET {column} = {column} {op} %(mask)s
             WHERE id = %(p_id)s
               AND {column} <> {column} {op} %(mask)s
         RETURNING {column}
        """.format(column=column, op=op), dict(mask=mask, p_id=self.id))
        if r is None:
            return 0
        self.set_attributes(**{column: r})
        return 1

    @cached_property
    def guessed_country(self):
        identity = self.get_current_identity()
        if identity:
            country = identity['postal_address'].get('country')
            if country:
                return country
        return self._guessed_country

    @property
    def _guessed_country(self):
        state = website.state.get(None)
        if state:
            locale, request = state['locale'], state['request']
            return locale.territory or request.source_country

    @property
    def can_attempt_payment(self):
        return (
            not self.is_suspended and
            self.status == 'active' and
            bool(self.get_email_address())
        )

    @property
    def marked_since(self):
        return self.db.one("""
            SELECT max(e.ts)
              FROM events e
             WHERE e.participant = %s
               AND e.type IN ('is_suspended', 'flags_changed')
        """, (self.id,))


class NeedConfirmation(Exception):
    """Represent the case where we need user confirmation during a merge.

    This is used in the workflow for merging one participant into another.

    """

    __slots__ = ()

    def __repr__(self):
        return "<NeedConfirmation>"
    __str__ = __repr__


def clean_up_closed_accounts():
    participants = website.db.all("""
        SELECT p, closed_time
          FROM (
                 SELECT p
                      , ( SELECT e2.ts
                            FROM events e2
                           WHERE e2.participant = p.id
                             AND e2.type = 'set_status'
                             AND e2.payload = '"closed"'
                        ORDER BY e2.ts DESC
                           LIMIT 1
                        ) AS closed_time
                   FROM participants p
                  WHERE p.status = 'closed'
                    AND p.kind IN ('individual', 'organization')
               ) a
         WHERE closed_time < (current_timestamp - INTERVAL '7 days')
           AND NOT EXISTS (
                   SELECT e.id
                     FROM events e
                    WHERE e.participant = (p).id
                      AND e.type = 'erase_personal_information'
                      AND e.ts > closed_time
               )
    """)
    for p, closed_time in participants:
        sleep(0.1)
        print("Deleting data of account ~%i (closed on %s)..." % (p.id, closed_time))
        p.erase_personal_information()
        p.invalidate_exchange_routes()
    return len(participants)


def free_up_usernames():
    n = website.db.one("""
        WITH updated AS (
            UPDATE participants
               SET username = '~' || id::text
             WHERE username NOT LIKE '~%'
               AND marked_as IN ('fraud', 'spam')
               AND kind IN ('individual', 'organization')
               AND (
                       SELECT e.ts
                         FROM events e
                        WHERE e.participant = participants.id
                          AND e.type = 'flags_changed'
                     ORDER BY e.ts DESC
                        LIMIT 1
                   ) < (current_timestamp - interval '3 weeks')
         RETURNING id
        ) SELECT count(*) FROM updated;
    """)
    print(f"Freed up {n} username{'s' if n > 1 else ''}.")


def send_account_disabled_notifications():
    """Notify the owners of accounts that have been flagged as fraud or spam.

    This is done to:
    - discourage fraudsters and spammers
    - encourage appeals when accounts have been mistakenly flagged

    The one hour delay before sending the notification gives time to reverse the decision.
    """
    participants = website.db.all("""
        SELECT DISTINCT ON (p.id) p
          FROM events e
          JOIN participants p ON p.id = e.participant
         WHERE e.type = 'flags_changed'
           AND ( e.payload->>'is_spam' = 'true' OR
                 e.payload->>'is_suspended' = 'true' OR
                 e.payload->>'marked_as' IN ('spam', 'fraud') )
           AND e.ts < (current_timestamp - interval '1 hour')
           AND e.ts > (current_timestamp - interval '48 hours')
           AND p.marked_as IN ('spam', 'fraud')
           AND NOT EXISTS (
                   SELECT 1
                     FROM notifications n
                    WHERE n.participant = p.id
                      AND n.event = 'account_disabled'
                      AND n.ts > (current_timestamp - interval '48 hours')
                    LIMIT 1
               )
      ORDER BY p.id
    """)
    sent = 0
    for p in participants:
        sleep(1)
        p.notify(
            'account_disabled',
            reason=p.marked_as,
            force_email=True,
        )
        sent += 1
    if sent:
        print(f"Sent {sent} account_disabled notification{'' if sent == 1 else 's'}.")
    return len(participants)


def generate_profile_description_missing_notifications():
    """Notify users who receive donations but don't have a profile description.
    """
    participants = website.db.all("""
        SELECT p
          FROM participants p
         WHERE p.status = 'active'
           AND p.kind IN ('individual', 'organization')
           AND p.receiving > 0
           AND ( p.goal IS NULL OR p.goal >= 0 )
           AND p.id NOT IN (SELECT DISTINCT participant FROM statements)
           AND p.id NOT IN (
                   SELECT DISTINCT n.participant
                     FROM notifications n
                    WHERE n.event = 'profile_description_missing'
                      AND n.ts >= (current_timestamp - interval '6 months')
               )
    """)
    for p in participants:
        sleep(1)
        p.notify('profile_description_missing', force_email=True)
    n = len(participants)
    participants = website.db.all("""
        SELECT DISTINCT p
          FROM payin_transfers pt
          JOIN participants p ON p.id = pt.recipient
         WHERE pt.status = 'awaiting_review'
           AND p.status = 'active'
           AND ( p.goal IS NULL OR p.goal >= 0 )
           AND p.id NOT IN (SELECT DISTINCT participant FROM statements)
           AND p.id NOT IN (
                   SELECT DISTINCT n.participant
                     FROM notifications n
                    WHERE n.event = 'profile_description_missing'
                      AND n.ts >= (current_timestamp - interval '1 week')
               )
    """)
    for p in participants:
        sleep(1)
        p.notify('profile_description_missing', force_email=True)
    n += len(participants)
    if n:
        s = '' if n == 1 else 's'
        print(f"Sent {n} profile_description_missing notification{s}.")
    return n
