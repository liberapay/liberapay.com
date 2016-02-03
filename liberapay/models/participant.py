from __future__ import print_function, unicode_literals

from base64 import b64decode, b64encode
from binascii import hexlify
from decimal import Decimal, ROUND_DOWN
from hashlib import pbkdf2_hmac, md5
from os import urandom
import pickle
from time import sleep
import uuid

from six.moves.urllib.parse import quote

from aspen.utils import utcnow
import aspen_jinja2_renderer
from markupsafe import escape as htmlescape
from postgres.orm import Model
from psycopg2 import IntegrityError
from psycopg2.extras import Json

import liberapay
from liberapay.billing import mangoapi
from liberapay.constants import (
    ASCII_ALLOWED_IN_USERNAME, EMAIL_RE, EMAIL_VERIFICATION_TIMEOUT, MAX_TIP,
    MIN_TIP, PASSWORD_MAX_SIZE, PASSWORD_MIN_SIZE, SESSION, SESSION_REFRESH,
    SESSION_TIMEOUT, USERNAME_MAX_SIZE
)
from liberapay.exceptions import (
    BadAmount,
    BadEmailAddress,
    BadPasswordSize,
    CannotRemovePrimaryEmail,
    EmailAlreadyTaken,
    EmailNotVerified,
    NonexistingElsewhere,
    NoSelfTipping,
    NoTippee,
    TooManyEmailAddresses,
    UserDoesntAcceptTips,
    UsernameAlreadyTaken,
    UsernameContainsInvalidCharacters,
    UsernameIsEmpty,
    UsernameIsRestricted,
    UsernameTooLong,
)
from liberapay.models._mixin_team import MixinTeam
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.community import Community
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.notifications import EVENTS
from liberapay.security.crypto import constant_time_compare
from liberapay.utils import (
    erase_cookie, set_cookie,
    emails, i18n,
)


class Participant(Model, MixinTeam):

    typname = 'participants'

    ANON = False

    def __eq__(self, other):
        if not isinstance(other, Participant):
            return False
        return self.id == other.id

    def __ne__(self, other):
        if not isinstance(other, Participant):
            return True
        return self.id != other.id

    def __repr__(self):
        return '<Participant %s>' % repr(self.username)


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
    def make_active(cls, username, kind, password, cursor=None):
        """Return a new active participant.
        """
        now = utcnow()
        d = {
            'kind': kind,
            'status': 'active',
            'password': cls.hash_password(password),
            'password_mtime': now,
            'join_time': now,
        }
        cols, vals = zip(*d.items())
        cols = ', '.join(cols)
        placeholders = ', '.join(['%s']*len(vals))
        with cls.db.get_cursor(cursor) as c:
            p = c.one("""
                INSERT INTO participants ({0}) VALUES ({1})
                  RETURNING participants.*::participants
            """.format(cols, placeholders), vals)
            p.change_username(username, c)
        return p

    def make_team(self, name):
        with self.db.get_cursor() as c:
            t = c.one("""
                INSERT INTO participants
                            (kind, status, join_time)
                     VALUES ('group', 'active', now())
                  RETURNING participants.*::participants
            """)
            t.change_username(name, c)
            t.add_member(self, c)
        return t

    @classmethod
    def from_id(cls, id):
        """Return an existing participant based on id.
        """
        return cls._from_thing("id", id)

    @classmethod
    def from_username(cls, username):
        """Return an existing participant based on username.
        """
        return cls._from_thing("lower(username)", username.lower())

    @classmethod
    def _from_thing(cls, thing, value):
        assert thing in ("id", "lower(username)", "mangopay_user_id")
        return cls.db.one("""
            SELECT participants.*::participants
              FROM participants
             WHERE {}=%s
        """.format(thing), (value,))

    @classmethod
    def authenticate(cls, k1, k2, v1=None, v2=None):
        assert k1 in ('id', 'username')
        if not (v1 and v2):
            return
        p = cls.db.one("""
            SELECT participants.*::participants
              FROM participants
             WHERE {0}=%s
        """.format(k1), (v1,))
        if not p:
            return
        if k2 == 'session':
            if not p.session_token:
                return
            if constant_time_compare(p.session_token, v2):
                p.authenticated = True
                return p
        elif k2 == 'password':
            if not p.password:
                return
            algo, rounds, salt, hashed = p.password.split('$', 3)
            rounds = int(rounds)
            salt, hashed = b64decode(salt), b64decode(hashed)
            if pbkdf2_hmac(algo, v2, salt, rounds) == hashed:
                p.authenticated = True
                return p

    def refetch(self):
        return self._from_thing('id', self.id)


    # Password Management
    # ===================

    @classmethod
    def hash_password(cls, password):
        l = len(password)
        if l < PASSWORD_MIN_SIZE or l > PASSWORD_MAX_SIZE:
            raise BadPasswordSize
        algo = 'sha256'
        salt = urandom(21)
        rounds = cls._password_rounds
        hashed = pbkdf2_hmac(algo, password, salt, rounds)
        hashed = '$'.join((algo, str(rounds), b64encode(salt), b64encode(hashed)))
        return hashed

    def update_password(self, password, cursor=None):
        hashed = self.hash_password(password)
        p_id = self.id
        with self.db.get_cursor(cursor) as c:
            c.run("""
                UPDATE participants
                   SET password = %(hashed)s
                     , password_mtime = CURRENT_TIMESTAMP
                 WHERE id = %(p_id)s;
            """, locals())


    # Session Management
    # ==================

    def update_session(self, new_token, expires):
        """Set ``session_token`` and ``session_expires``.
        """
        self.db.run("""
            UPDATE participants
               SET session_token=%s
                 , session_expires=%s
             WHERE id=%s
               AND is_suspicious IS NOT true
        """, (new_token, expires, self.id))
        self.set_attributes(session_token=new_token, session_expires=expires)

    def set_session_expires(self, expires):
        """Set ``session_expires`` to the given datetime.
        """
        self.db.run( "UPDATE participants SET session_expires=%s "
                     "WHERE id=%s AND is_suspicious IS NOT true"
                   , (expires, self.id,)
                    )
        self.set_attributes(session_expires=expires)

    def sign_in(self, cookies):
        """Start a new session for the user.
        """
        assert self.authenticated
        token = uuid.uuid4().hex
        expires = utcnow() + SESSION_TIMEOUT
        self.update_session(token, expires)
        creds = '%s:%s' % (self.id, token)
        set_cookie(cookies, SESSION, creds, expires)

    def keep_signed_in(self, cookies):
        """Extend the user's current session.
        """
        new_expires = utcnow() + SESSION_TIMEOUT
        if new_expires - self.session_expires > SESSION_REFRESH:
            self.set_session_expires(new_expires)
            token = self.session_token
            creds = '%s:%s' % (self.id, token)
            set_cookie(cookies, SESSION, creds, expires=new_expires)

    def sign_out(self, cookies):
        """End the user's current session.
        """
        self.update_session(None, None)
        erase_cookie(cookies, SESSION)


    # Suspiciousness
    # ==============

    @property
    def is_whitelisted(self):
        return self.is_suspicious is False


    # Statement
    # =========

    def get_statement(self, langs, type='profile'):
        """Get the participant's statement in the language that best matches
        the list provided.
        """
        p_id = self.id
        return self.db.one("""
            SELECT content, lang
              FROM statements
              JOIN enumerate(%(langs)s) langs ON langs.value = statements.lang
             WHERE participant = %(p_id)s
               AND type = %(type)s
          ORDER BY langs.rank
             LIMIT 1
        """, locals(), default=(None, None))

    def get_statement_langs(self, type='profile'):
        return self.db.all("""
            SELECT lang FROM statements WHERE participant=%s AND type=%s
        """, (self.id, type))

    def upsert_statement(self, lang, statement, type='profile'):
        if not statement:
            self.db.run("""
                DELETE FROM statements
                 WHERE participant=%s
                   AND type=%s
                   AND lang=%s
            """, (self.id, type, lang))
            return
        r = self.db.one("""
            UPDATE statements
               SET content=%s
             WHERE participant=%s
               AND type=%s
               AND lang=%s
         RETURNING true
        """, (statement, self.id, type, lang))
        if not r:
            search_conf = i18n.SEARCH_CONFS.get(lang, 'simple')
            try:
                self.db.run("""
                    INSERT INTO statements
                                (lang, content, participant, search_conf, type)
                         VALUES (%s, %s, %s, %s, %s)
                """, (lang, statement, self.id, search_conf, type))
            except IntegrityError:
                return self.upsert_statement(lang, statement)


    # Pricing
    # =======

    @property
    def usage(self):
        return max(self.giving, self.receiving)

    @property
    def suggested_payment(self):
        return (self.usage * Decimal('0.05')).quantize(Decimal('.01'))


    # Stubs
    # =====

    def resolve_stub(self):
        rec = self.db.one("""
            SELECT platform, user_name
              FROM elsewhere
             WHERE participant = %s
        """, (self.id,))
        return rec and '/on/%s/%s/' % (rec.platform, rec.user_name)


    # Closing
    # =======

    class AccountNotEmpty(Exception): pass

    def final_check(self, cursor):
        """Sanity-check that balance and tips have been dealt with.
        """
        if self.balance != 0:
            raise self.AccountNotEmpty
        incoming = cursor.one("""
            SELECT count(*) FROM current_tips WHERE tippee = %s AND amount > 0
        """, (self.id,))
        if incoming > 0:
            raise self.AccountNotEmpty

    class UnknownDisbursementStrategy(Exception): pass

    def close(self, disbursement_strategy):
        """Close the participant's account.
        """
        with self.db.get_cursor() as cursor:
            if disbursement_strategy == None:
                pass  # No balance, supposedly. final_check will make sure.
            elif disbursement_strategy == 'downstream':
                # This in particular needs to come before clear_tips_giving.
                self.distribute_balance_as_final_gift(cursor)
            else:
                raise self.UnknownDisbursementStrategy

            self.clear_tips_giving(cursor)
            self.clear_tips_receiving(cursor)
            self.clear_takes(cursor)
            if self.kind == 'group':
                self.remove_all_members(cursor)
            self.clear_personal_information(cursor)
            self.final_check(cursor)
            self.update_status('closed', cursor)

    class NoOneToGiveFinalGiftTo(Exception): pass

    def distribute_balance_as_final_gift(self, cursor):
        """Distribute a balance as a final gift.
        """
        if self.balance == 0:
            return

        tips, total, _, _= self.get_giving_for_profile()
        transfers = []
        distributed = Decimal('0.00')

        for tip in tips:
            rate = tip.amount / total
            pro_rated = (self.balance * rate).quantize(Decimal('0.01'), ROUND_DOWN)
            if pro_rated == 0:
                continue
            distributed += pro_rated
            transfers.append([tip.tippee, pro_rated])

        if not transfers:
            raise self.NoOneToGiveFinalGiftTo

        diff = self.balance - distributed
        if diff != 0:
            transfers[0][1] += diff  # Give it to the highest receiver.

        from liberapay.billing.exchanges import transfer
        db = self.db
        tipper = self.id
        for tippee, amount in transfers:
            balance = transfer(db, tipper, tippee, amount, 'final-gift',
                               tipper_mango_id=self.mangopay_user_id,
                               tipper_wallet_id=self.mangopay_wallet_id)

        assert balance == 0
        self.set_attributes(balance=balance)

    def clear_tips_giving(self, cursor):
        """Zero out tips from a given user.
        """
        tippees = cursor.all("""

            SELECT ( SELECT p.*::participants
                       FROM participants p
                      WHERE p.id=t.tippee
                    ) AS tippee
              FROM current_tips t
             WHERE tipper = %s
               AND amount > 0

        """, (self.id,))
        for tippee in tippees:
            self.set_tip_to(tippee, '0.00', update_self=False, cursor=cursor)

    def clear_tips_receiving(self, cursor):
        """Zero out tips to a given user.
        """
        tippers = cursor.all("""

            SELECT ( SELECT p.*::participants
                       FROM participants p
                      WHERE p.id=t.tipper
                    ) AS tipper
              FROM current_tips t
             WHERE tippee = %s
               AND amount > 0

        """, (self.id,))
        for tipper in tippers:
            tipper.set_tip_to(self, '0.00', update_tippee=False, cursor=cursor)

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
            t.set_take_for(self, None, self, cursor)

    def clear_personal_information(self, cursor):
        """Clear personal information such as statements and goal.
        """
        r = cursor.one("""

            DELETE FROM community_memberships WHERE participant=%(id)s;
            DELETE FROM community_subscriptions WHERE participant=%(id)s;
            DELETE FROM emails WHERE participant=%(id)s AND address <> %(email)s;
            DELETE FROM statements WHERE participant=%(id)s;

            UPDATE participants
               SET goal=NULL
                 , avatar_url=NULL
                 , session_token=NULL
                 , session_expires=now()
                 , giving=0
                 , receiving=0
                 , npatrons=0
             WHERE id=%(id)s
         RETURNING *;

        """, dict(id=self.id, email=self.email))
        self.set_attributes(**r._asdict())

    @property
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


    # Emails
    # ======

    def add_email(self, email, cursor=None):
        """
            This is called when
            1) Adding a new email address
            2) Resending the verification email for an unverified email address

            Returns the number of emails sent.
        """

        if not EMAIL_RE.match(email):
            raise BadEmailAddress(email)

        # Check that this address isn't already verified
        owner = (cursor or self.db).one("""
            SELECT participant
              FROM emails
             WHERE address = %(email)s
               AND verified IS true
        """, locals())
        if owner:
            if owner == self.id:
                return 0
            else:
                raise EmailAlreadyTaken(email)

        if len(self.get_emails()) > 9:
            raise TooManyEmailAddresses(email)

        nonce = str(uuid.uuid4())
        added_time = utcnow()
        try:
            with self.db.get_cursor(cursor) as c:
                self.add_event(c, 'add_email', email)
                c.run("""
                    INSERT INTO emails
                                (address, nonce, added_time, participant)
                         VALUES (%s, %s, %s, %s)
                """, (email, nonce, added_time, self.id))
        except IntegrityError:
            nonce = (cursor or self.db).one("""
                UPDATE emails
                   SET added_time=%s
                 WHERE participant=%s
                   AND address=%s
                   AND verified IS NULL
             RETURNING nonce
            """, (added_time, self.id, email))
            if not nonce:
                return self.add_email(email)

        scheme = liberapay.canonical_scheme
        host = liberapay.canonical_host
        username = self.username
        quoted_email = quote(email)
        link = "{scheme}://{host}/{username}/emails/verify.html?email={quoted_email}&nonce={nonce}"
        r = self.send_email('verification', email=email, link=link.format(**locals()))
        assert r == 1 # Make sure the verification email was sent

        if self.email:
            self.send_email('verification_notice', new_email=email)
            return 2
        else:
            gravatar_id = md5(email.strip().lower()).hexdigest()
            gravatar_url = 'https://secure.gravatar.com/avatar/'+gravatar_id
            (cursor or self.db).run("""
                UPDATE participants
                   SET avatar_url = %s
                 WHERE id = %s
            """, (gravatar_url, self.id))
            self.set_attributes(avatar_url=gravatar_url)

        return 1

    def update_email(self, email):
        if not getattr(self.get_email(email), 'verified', False):
            raise EmailNotVerified(email)
        id = self.id
        with self.db.get_cursor() as c:
            self.add_event(c, 'set_primary_email', email)
            c.run("""
                UPDATE participants
                   SET email=%(email)s
                 WHERE id=%(id)s
            """, locals())
        self.set_attributes(email=email)

    def verify_email(self, email, nonce):
        if '' in (email, nonce):
            return emails.VERIFICATION_MISSING
        r = self.get_email(email)
        if r is None:
            return emails.VERIFICATION_FAILED
        if r.verified:
            assert r.nonce is None  # and therefore, order of conditions matters
            return emails.VERIFICATION_REDUNDANT
        if not constant_time_compare(r.nonce, nonce):
            return emails.VERIFICATION_FAILED
        if (utcnow() - r.added_time) > EMAIL_VERIFICATION_TIMEOUT:
            return emails.VERIFICATION_EXPIRED
        try:
            self.db.run("""
                UPDATE emails
                   SET verified=true, verified_time=now(), nonce=NULL
                 WHERE participant=%s
                   AND address=%s
                   AND verified IS NULL
            """, (self.id, email))
        except IntegrityError:
            return emails.VERIFICATION_STYMIED

        if not self.email:
            self.update_email(email)
        return emails.VERIFICATION_SUCCEEDED

    def get_email(self, email):
        return self.db.one("""
            SELECT *
              FROM emails
             WHERE participant=%s
               AND address=%s
        """, (self.id, email))

    def get_emails(self):
        return self.db.all("""
            SELECT *
              FROM emails
             WHERE participant=%s
          ORDER BY id
        """, (self.id,))

    def remove_email(self, address):
        if address == self.email:
            raise CannotRemovePrimaryEmail()
        with self.db.get_cursor() as c:
            self.add_event(c, 'remove_email', address)
            c.run("DELETE FROM emails WHERE participant=%s AND address=%s",
                  (self.id, address))

    def send_email(self, spt_name, **context):
        context.update(aspen_jinja2_renderer.Renderer.global_context)
        context['participant'] = self
        context['username'] = self.username
        context['button_style'] = (
            "color: #fff; text-decoration:none; display:inline-block; "
            "padding: 0 15px; background: #396; white-space: nowrap; "
            "font: normal 14px/40px Arial, sans-serif; border-radius: 3px"
        )
        email = context.setdefault('email', self.email)
        if not email:
            return 0 # Not Sent
        langs = i18n.parse_accept_lang(self.email_lang or 'en')
        locale = i18n.match_lang(langs)
        i18n.add_helpers_to_context(self._tell_sentry, context, locale)
        context['escape'] = lambda s: s
        context_html = dict(context)
        i18n.add_helpers_to_context(self._tell_sentry, context_html, locale)
        context_html['escape'] = htmlescape
        spt = self._emails[spt_name]
        base_spt = self._emails['base']
        def render(t, context):
            b = base_spt[t].render(context).strip()
            return b.replace('$body', spt[t].render(context).strip())
        message = {}
        message['from_email'] = 'support@liberapay.com'
        message['from_name'] = 'Liberapay Support'
        message['to'] = [{'email': email, 'name': self.username}]
        message['subject'] = spt['subject'].render(context).strip()
        message['html'] = render('text/html', context_html)
        message['text'] = render('text/plain', context)

        self._mailer.messages.send(message=message)
        return 1 # Sent

    def queue_email(self, spt_name, **context):
        context = b'\\x' + hexlify(pickle.dumps(context, 2))
        self.db.run("""
            INSERT INTO email_queue
                        (participant, spt_name, context)
                 VALUES (%s, %s, %s)
        """, (self.id, spt_name, context))

    @classmethod
    def dequeue_emails(cls):
        fetch_messages = lambda: cls.db.all("""
            SELECT *
              FROM email_queue
          ORDER BY id ASC
             LIMIT 60
        """)
        while True:
            messages = fetch_messages()
            if not messages:
                break
            for msg in messages:
                p = cls.from_id(msg.participant)
                r = p.send_email(msg.spt_name, **pickle.loads(msg.context))
                cls.db.run("DELETE FROM email_queue WHERE id = %s", (msg.id,))
                if r == 1:
                    sleep(1)

    def set_email_lang(self, accept_lang):
        if not accept_lang:
            return
        self.db.run("UPDATE participants SET email_lang=%s WHERE id=%s",
                    (accept_lang, self.id))
        self.set_attributes(email_lang=accept_lang)


    # Notifications
    # =============

    def notify(self, event, web=True, **context):
        if web:
            self.add_notification(event, **context)
        if self.email_notif_bits & EVENTS.get(event).bit:
            self.queue_email(event, **context)

    def add_notification(self, event, **context):
        p_id = self.id
        context = b'\\x' + hexlify(pickle.dumps(context, 2))
        n_id = self.db.one("""
            INSERT INTO notification_queue
                        (participant, event, context)
                 VALUES (%(p_id)s, %(event)s, %(context)s)
              RETURNING id;
        """, locals())
        pending_notifs = self.db.one("""
            UPDATE participants
               SET pending_notifs = pending_notifs + 1
             WHERE id = %(p_id)s
         RETURNING pending_notifs;
        """, locals())
        self.set_attributes(pending_notifs=pending_notifs)
        return n_id

    def remove_notification(self, n_id):
        p_id = self.id
        r = self.db.one("""
            DO $$
            BEGIN
                DELETE FROM notification_queue
                 WHERE id = %(n_id)s
                   AND participant = %(p_id)s;
                IF (NOT FOUND) THEN RETURN; END IF;
                UPDATE participants
                   SET pending_notifs = pending_notifs - 1
                 WHERE id = %(p_id)s;
            END;
            $$ LANGUAGE plpgsql;

            SELECT pending_notifs
              FROM participants
             WHERE id = %(p_id)s;
        """, locals())
        self.set_attributes(pending_notifs=r)

    def render_notifications(self, state):
        r = []
        if not self.pending_notifs:
            return r
        notifs = self.db.all("""
            SELECT id, event, context
              FROM notification_queue
             WHERE participant = %s
        """, (self.id,))
        escape = state['escape']
        state['escape'] = lambda a: a
        for id, event, context in notifs:
            try:
                context = dict(state, **pickle.loads(context))
                spt = self._emails[event]
                html = spt['text/html'].render(context).strip()
                typ = context.get('type', 'info')
                r.append(dict(id=id, html=html, type=typ))
            except Exception as e:
                self._tell_sentry(e, state)
        state['escape'] = escape
        return r

    def notify_patrons(self, elsewhere, tips):
        for t in tips:
            Participant.from_id(t.tipper).notify(
                'pledgee_joined',
                user_name=elsewhere.user_name,
                platform=elsewhere.platform_data.display_name,
                amount=t.amount,
                profile_url=elsewhere.liberapay_url,
            )


    # Exchange-related stuff
    # ======================

    def get_bank_account_error(self):
        return getattr(ExchangeRoute.from_network(self, 'mango-ba'), 'error', None)

    def get_credit_card_error(self):
        return getattr(ExchangeRoute.from_network(self, 'mango-cc'), 'error', None)

    @property
    def withdrawable_balance(self):
        from liberapay.billing.exchanges import QUARANTINE
        return self.db.one("""
            SELECT COALESCE(sum(amount), 0)
              FROM cash_bundles
             WHERE owner = %s
               AND ts < now() - INTERVAL %s
        """, (self.id, QUARANTINE))


    # Random Stuff
    # ============

    def add_event(self, c, type, payload, recorder=None):
        c.run("""
            INSERT INTO events (participant, type, payload, recorder)
            VALUES (%s, %s, %s, %s)
        """, (self.id, type, Json(payload), recorder))

    def url(self, path=''):
        scheme = liberapay.canonical_scheme
        host = liberapay.canonical_host
        username = self.username
        return '{scheme}://{host}/{username}/{path}'.format(**locals())

    def get_teams(self):
        """Return a list of teams this user is a member of.
        """
        return self.db.all("""

            SELECT team AS id
                 , p.username AS name
                 , ( SELECT count(*)
                       FROM current_takes
                      WHERE team=x.team
                    ) AS nmembers
              FROM current_takes x
              JOIN participants p ON p.id = x.team
             WHERE member=%s;

        """, (self.id,))

    @property
    def accepts_tips(self):
        return (self.goal is None) or (self.goal >= 0)


    # Communities
    # ===========

    def create_community(self, name, **kw):
        return Community.create(name, self.id, **kw)

    def update_community_status(self, table, on, c_id):
        assert table in ('memberships', 'subscriptions')
        p_id = self.id
        self.db.run("""
            DO $$
            DECLARE
                cname text;
            BEGIN
                BEGIN
                    INSERT INTO community_{0}
                                (community, participant, is_on)
                         VALUES (%(c_id)s, %(p_id)s, %(on)s);
                    IF (FOUND) THEN RETURN; END IF;
                EXCEPTION WHEN unique_violation THEN
                    GET STACKED DIAGNOSTICS cname = CONSTRAINT_NAME;
                    IF (cname <> 'community_{0}_participant_community_key') THEN
                        RAISE;
                    END IF;
                END;
                UPDATE community_{0}
                   SET is_on = %(on)s
                     , mtime = CURRENT_TIMESTAMP
                 WHERE community = %(c_id)s
                   AND participant = %(p_id)s;
                IF (NOT FOUND) THEN
                    RAISE 'upsert in community_{0} failed';
                END IF;
            END;
            $$ LANGUAGE plpgsql;
        """.format(table), locals())


    def get_communities(self):
        return self.db.all("""
            SELECT c.*, replace(c.name, '_', ' ') AS pretty_name
              FROM community_memberships cm
              JOIN communities c ON c.id = cm.community
             WHERE cm.is_on AND cm.participant = %s
          ORDER BY c.nmembers ASC, c.name
        """, (self.id,))


    # More Random Stuff
    # =================

    def change_username(self, suggested, cursor=None):
        suggested = suggested and suggested.strip()

        if not suggested:
            raise UsernameIsEmpty(suggested)

        if len(suggested) > USERNAME_MAX_SIZE:
            raise UsernameTooLong(suggested)

        if set(suggested) - ASCII_ALLOWED_IN_USERNAME:
            raise UsernameContainsInvalidCharacters(suggested)

        lowercased = suggested.lower()

        if lowercased in liberapay.RESTRICTED_USERNAMES:
            raise UsernameIsRestricted(suggested)

        if suggested != self.username:
            with self.db.get_cursor(cursor) as c:
                try:
                    # Will raise IntegrityError if the desired username is taken.
                    actual = c.one("""
                        UPDATE participants
                           SET username=%s
                         WHERE id=%s
                     RETURNING username, lower(username)
                    """, (suggested, self.id))
                except IntegrityError:
                    raise UsernameAlreadyTaken(suggested)

                self.add_event(c, 'set_username', suggested)
                assert (suggested, lowercased) == actual # sanity check
                self.set_attributes(username=suggested)

        return suggested

    def update_avatar(self):
        if self.status != 'stub':
            return
        avatar_url = self.db.run("""
            UPDATE participants p
               SET avatar_url = (
                       SELECT avatar_url
                         FROM elsewhere
                        WHERE participant = p.id
                     ORDER BY platform = 'github' DESC,
                              avatar_url LIKE '%%gravatar.com%%' DESC
                        LIMIT 1
                   )
             WHERE p.id = %s
         RETURNING avatar_url
        """, (self.id,))
        self.set_attributes(avatar_url=avatar_url)

    def update_goal(self, goal, cursor=None):
        with self.db.get_cursor(cursor) as c:
            json = None if goal is None else str(goal)
            self.add_event(c, 'set_goal', json)
            c.run("UPDATE participants SET goal=%s WHERE id=%s", (goal, self.id))
            self.set_attributes(goal=goal)
            if not self.accepts_tips:
                self.clear_tips_receiving(c)
                self.update_receiving(c)

    def update_status(self, status, cursor=None):
        with self.db.get_cursor(cursor) as c:
            r = c.one("""
                UPDATE participants
                   SET status = %(status)s
                     , join_time = COALESCE(join_time, CURRENT_TIMESTAMP)
                 WHERE id=%(id)s
                   AND status <> %(status)s
             RETURNING status, join_time
            """, dict(id=self.id, status=status))
            if not r:
                return
            self.set_attributes(**r._asdict())
            self.add_event(c, 'set_status', status)
            if status == 'closed':
                self.update_goal(-1, c)
            elif status == 'active':
                self.update_goal(None, c)

    def update_giving_and_tippees(self, cursor):
        updated_tips = self.update_giving(cursor)
        for tip in updated_tips:
            Participant.from_id(tip.tippee).update_receiving(cursor)

    def update_giving(self, cursor=None):
        # Update is_funded on tips
        tips = (cursor or self.db).all("""
            SELECT t.*
              FROM current_tips t
              JOIN participants p2 ON p2.id = t.tippee
             WHERE t.tipper = %s
               AND t.amount > 0
               AND p2.is_suspicious IS NOT true
          ORDER BY p2.join_time IS NULL, t.ctime ASC
        """, (self.id,))
        fake_balance = self.balance + self.receiving
        updated = []
        for tip in tips:
            if tip.amount > fake_balance:
                is_funded = False
            else:
                fake_balance -= tip.amount
                is_funded = True
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
               SET giving = COALESCE((
                     SELECT sum(amount)
                       FROM current_tips
                       JOIN participants p2 ON p2.id = tippee
                      WHERE tipper = %(id)s
                        AND p2.is_suspicious IS NOT true
                        AND p2.status = 'active'
                        AND (p2.mangopay_user_id IS NOT NULL OR kind = 'group')
                        AND amount > 0
                        AND is_funded
                   ), 0)
             WHERE p.id = %(id)s
         RETURNING giving
        """, dict(id=self.id))
        self.set_attributes(giving=giving)

        return updated

    def update_receiving(self, cursor=None):
        if self.kind == 'group':
            old_takes = self.compute_actual_takes(cursor=cursor)
        r = (cursor or self.db).one("""
            WITH our_tips AS (
                     SELECT amount
                       FROM current_tips
                       JOIN participants p2 ON p2.id = tipper
                      WHERE tippee = %(id)s
                        AND p2.is_suspicious IS NOT true
                        AND amount > 0
                        AND is_funded
                 )
            UPDATE participants p
               SET receiving = (COALESCE((
                       SELECT sum(amount)
                         FROM our_tips
                   ), 0) + taking)
                 , npatrons = COALESCE((SELECT count(*) FROM our_tips), 0)
             WHERE p.id = %(id)s
         RETURNING receiving, npatrons
        """, dict(id=self.id))
        self.set_attributes(receiving=r.receiving, npatrons=r.npatrons)
        if self.kind == 'group':
            new_takes = self.compute_actual_takes(cursor=cursor)
            self.update_taking(old_takes, new_takes, cursor=cursor)


    def set_tip_to(self, tippee, amount, update_self=True, update_tippee=True, cursor=None):
        """Given a Participant or username, and amount as str, returns a dict.

        We INSERT instead of UPDATE, so that we have history to explore. The
        COALESCE function returns the first of its arguments that is not NULL.
        The effect here is to stamp all tips with the timestamp of the first
        tip from this user to that. I believe this is used to determine the
        order of transfers during payday.

        The dict returned represents the row inserted in the tips table, with
        an additional boolean indicating whether this is the first time this
        tipper has tipped (we want to track that as part of our conversion
        funnel).

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

        amount = Decimal(amount)  # May raise InvalidOperation
        if amount != 0 and amount < MIN_TIP or amount > MAX_TIP:
            raise BadAmount(amount)

        if not tippee.accepts_tips and amount != 0:
            raise UserDoesntAcceptTips(tippee.username)

        # Insert tip
        NEW_TIP = """\

            INSERT INTO tips
                        (ctime, tipper, tippee, amount)
                 VALUES ( COALESCE (( SELECT ctime
                                        FROM tips
                                       WHERE (tipper=%(tipper)s AND tippee=%(tippee)s)
                                       LIMIT 1
                                      ), CURRENT_TIMESTAMP)
                        , %(tipper)s, %(tippee)s, %(amount)s
                         )
              RETURNING *
                      , ( SELECT count(*) = 0 FROM tips WHERE tipper=%(tipper)s ) AS first_time_tipper
                      , ( SELECT join_time IS NULL FROM participants WHERE id = %(tippee)s ) AS is_pledge

        """
        args = dict(tipper=self.id, tippee=tippee.id, amount=amount)
        t = (cursor or self.db).one(NEW_TIP, args)._asdict()

        if update_self:
            # Update giving amount of tipper
            updated = self.update_giving(cursor)
            for u in updated:
                if u.id == t['id']:
                    t['is_funded'] = u.is_funded
        if update_tippee:
            # Update receiving amount of tippee
            tippee.update_receiving(cursor)

        return t


    @staticmethod
    def _zero_tip_dict(tippee):
        if isinstance(tippee, Participant):
            tippee = tippee.id
        return dict(amount=Decimal('0.00'), is_funded=False, tippee=tippee)


    def get_tip_to(self, tippee):
        """Given a participant (or their id), returns a dict.
        """
        default = self._zero_tip_dict(tippee)
        tippee = default['tippee']
        if self.id == tippee:
            return default
        return self.db.one("""\

            SELECT *
              FROM tips
             WHERE tipper=%s
               AND tippee=%s
          ORDER BY mtime DESC
             LIMIT 1

        """, (self.id, tippee), back_as=dict, default=default)


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
                    proportion_of_tips_at_this_amount,
                    proportion_of_total_amount_at_this_amount
                ]

        """
        SQL = """

            SELECT amount
                 , count(amount) AS ncontributing
              FROM ( SELECT DISTINCT ON (tipper)
                            amount
                          , tipper
                       FROM tips
                       JOIN participants p ON p.id = tipper
                      WHERE tippee=%s
                        AND is_funded
                        AND is_suspicious IS NOT true
                   ORDER BY tipper
                          , mtime DESC
                    ) AS foo
             WHERE amount > 0
          GROUP BY amount
          ORDER BY amount

        """

        tip_amounts = []

        npatrons = 0.0  # float to trigger float division
        contributed = Decimal('0.00')
        for rec in self.db.all(SQL, (self.id,)):
            tip_amounts.append([ rec.amount
                               , rec.ncontributing
                               , rec.amount * rec.ncontributing
                                ])
            contributed += tip_amounts[-1][2]
            npatrons += rec.ncontributing

        for row in tip_amounts:
            row.append((row[1] / npatrons) if npatrons > 0 else 0)
            row.append((row[2] / contributed) if contributed > 0 else 0)

        return tip_amounts, npatrons, contributed


    def get_giving_for_profile(self):

        tips = self.db.all("""\

            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , t.mtime
                     , p.join_time
                     , p.username
                     , p.kind
                     , t.is_funded
                     , (p.mangopay_user_id IS NOT NULL OR kind = 'group') AS is_identified
                     , p.is_suspicious
                  FROM tips t
                  JOIN participants p ON p.id = t.tippee
                 WHERE tipper = %s
                   AND p.status = 'active'
              ORDER BY tippee
                     , t.mtime DESC
            ) AS foo
            ORDER BY amount DESC
                   , username

        """, (self.id,))

        pledges = self.db.all("""\

            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , t.mtime
                     , p.join_time
                     , p.username
                     , e.platform
                     , e.user_name
                  FROM tips t
                  JOIN participants p ON p.id = t.tippee
                  JOIN elsewhere e ON e.participant = t.tippee
                 WHERE tipper = %s
                   AND p.status = 'stub'
              ORDER BY tippee
                     , t.mtime DESC
            ) AS foo
            ORDER BY amount DESC
                   , lower(user_name)

        """, (self.id,))


        # Compute the total

        total = sum([t.amount for t in tips])
        if not total:
            # If tips is an empty list, total is int 0. We want a Decimal.
            total = Decimal('0.00')

        pledges_total = sum([t.amount for t in pledges])
        if not pledges_total:
            pledges_total = Decimal('0.00')

        return tips, total, pledges, pledges_total

    def get_tips_receiving(self):
        return self.db.all("""
            SELECT *
              FROM current_tips
             WHERE tippee=%s
               AND amount>0
        """, (self.id,))

    def get_current_tips(self):
        """Get the tips this participant is currently sending to others.
        """
        return self.db.all("""
            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , p.username
                     , p.join_time
                  FROM tips t
                  JOIN participants p ON p.id = t.tippee
                 WHERE tipper = %s
                   AND p.is_suspicious IS NOT true
              ORDER BY tippee
                     , t.mtime DESC
            ) AS foo
            ORDER BY amount DESC
                   , tippee
        """, (self.id,), back_as=dict)


    def get_age_in_seconds(self):
        if self.join_time is not None:
            return (utcnow() - self.join_time).total_seconds()
        return -1


    def get_account_elsewhere(self, platform):
        """Return an AccountElsewhere instance.
        """
        return self.db.one("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE participant=%s
               AND platform=%s

        """, (self.id, platform))


    def get_accounts_elsewhere(self):
        """Return a dict of AccountElsewhere instances.
        """
        accounts = self.db.all("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE participant=%s

        """, (self.id,))
        accounts_dict = {account.platform: account for account in accounts}
        return accounts_dict


    def get_mangopay_account(self):
        """Fetch the mangopay account for this participant.
        """
        if not self.mangopay_user_id:
            return
        return mangoapi.users.Get(self.mangopay_user_id)


    def take_over(self, account, have_confirmation=False):
        """Given an AccountElsewhere or a tuple (platform_name, user_id),
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
            platform, user_id = account.platform, account.user_id
        else:
            platform, user_id = map(str, account)

        CREATE_TEMP_TABLE_FOR_TIPS = """
            CREATE TEMP TABLE temp_tips ON COMMIT drop AS
                SELECT ctime, tipper, tippee, amount, is_funded
                  FROM current_tips
                 WHERE (tippee = %(dead)s OR tippee = %(live)s)
                   AND amount > 0;
        """

        CONSOLIDATE_TIPS_RECEIVING = """
            -- Create a new set of tips, one for each current tip *to* either
            -- the dead or the live account. If a user was tipping both the
            -- dead and the live account, then we create one new combined tip
            -- to the live account (via the GROUP BY and sum()).
            INSERT INTO tips (ctime, tipper, tippee, amount, is_funded)
                 SELECT min(ctime), tipper, %(live)s AS tippee, sum(amount), bool_and(is_funded)
                   FROM temp_tips
                  WHERE (tippee = %(dead)s OR tippee = %(live)s)
                        -- Include tips *to* either the dead or live account.
                AND NOT (tipper = %(dead)s OR tipper = %(live)s)
                        -- Don't include tips *from* the dead or live account,
                        -- lest we convert cross-tipping to self-tipping.
               GROUP BY tipper
        """

        ZERO_OUT_OLD_TIPS_RECEIVING = """
            INSERT INTO tips (ctime, tipper, tippee, amount)
                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM temp_tips
                 WHERE tippee=%s
        """

        with self.db.get_cursor() as cursor:

            # Load the existing connection
            # Every account elsewhere has at least a stub participant account
            # on Liberapay.
            elsewhere = cursor.one("""
                SELECT e.*::elsewhere_with_participant
                  FROM elsewhere e
                  JOIN participants p ON p.id = e.participant
                 WHERE e.platform=%s AND e.user_id=%s
            """, (platform, user_id), default=Exception)
            other = elsewhere.participant

            if self.id == other.id:
                # this is a no op - trying to take over itself
                return

            # Save old tips so we can notify patrons that they've been claimed
            old_tips = other.get_tips_receiving() if other.status == 'stub' else None

            # Make sure we have user confirmation if needed.
            # ==============================================
            # We need confirmation if any of these are true:
            #
            #   - the other participant is not a stub; we are taking the
            #       account elsewhere away from another viable participant
            #
            #   - we already have an account elsewhere connected from the given
            #       platform, and it will be handed off to a new stub
            #       participant

            other_is_a_real_participant = other.status != 'stub'

            we_already_have_that_kind_of_account = cursor.one("""
                SELECT true
                  FROM elsewhere
                 WHERE participant=%s AND platform=%s
            """, (self.id, platform), default=False)

            need_confirmation = NeedConfirmation(
                other_is_a_real_participant,
                we_already_have_that_kind_of_account,
            )
            if need_confirmation and not have_confirmation:
                raise need_confirmation

            # Move any old account out of the way
            if we_already_have_that_kind_of_account:
                new_stub = Participant.make_stub(cursor)
                cursor.run( "UPDATE elsewhere SET participant=%s "
                            "WHERE platform=%s AND participant=%s"
                          , (new_stub.id, platform, self.id)
                           )

            # Do the deal
            cursor.run( "UPDATE elsewhere SET participant=%s "
                        "WHERE platform=%s AND user_id=%s"
                      , (self.id, platform, user_id)
                       )

            # Turn pledges into actual tips
            if old_tips:
                x, y = self.id, other.id
                cursor.run(CREATE_TEMP_TABLE_FOR_TIPS, dict(live=x, dead=y))
                cursor.run(CONSOLIDATE_TIPS_RECEIVING, dict(live=x, dead=y))
                cursor.run(ZERO_OUT_OLD_TIPS_RECEIVING, (other.id,))

            # Try to delete the stub account, or prevent new pledges to it
            if not other_is_a_real_participant:
                cursor.run("""
                    DO $$
                    BEGIN
                        DELETE FROM participants WHERE id = %(dead)s;
                    EXCEPTION WHEN OTHERS THEN
                        UPDATE participants
                           SET goal = -1
                         WHERE id = %(dead)s;
                    END;
                    $$ LANGUAGE plpgsql;
                """, dict(dead=other.id))

            # Log the event
            payload = dict(platform=platform, user_id=user_id, owner=other.id)
            self.add_event(cursor, 'take-over', payload)

        if old_tips:
            self.notify_patrons(elsewhere, tips=old_tips)

        self.update_avatar()

        # Note: the order matters here, receiving needs to be updated before giving
        self.update_receiving()
        self.update_giving()

    def delete_elsewhere(self, platform, user_id):
        """Deletes account elsewhere unless the user would not be able
        to log in anymore.
        """
        user_id = str(user_id)
        with self.db.get_cursor() as c:
            c.one("""
                DELETE FROM elsewhere
                WHERE participant=%s
                AND platform=%s
                AND user_id=%s
                RETURNING participant
            """, (self.id, platform, user_id), default=NonexistingElsewhere)
            self.add_event(c, 'delete_elsewhere', dict(platform=platform, user_id=user_id))
        self.update_avatar()

    def to_dict(self, details=False, inquirer=None):
        output = { 'id': self.id
                 , 'username': self.username
                 , 'avatar': self.avatar_url
                 , 'kind': self.kind
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
            if self.goal > 0:
                goal = str(self.goal)
            else:
                goal = None
            output['goal'] = goal

        # Key: receiving
        # Values:
        #   null - user is receiving anonymously
        #   3.00 - user receives this amount in tips
        if not self.hide_receiving:
            receiving = str(self.receiving)
        else:
            receiving = None
        output['receiving'] = receiving

        # Key: giving
        # Values:
        #   null - user is giving anonymously
        #   3.00 - user gives this amount in tips
        if not self.hide_giving:
            giving = str(self.giving)
        else:
            giving = None
        output['giving'] = giving

        # Key: my_tip
        # Values:
        #   undefined - user is not authenticated
        #   "self" - user == participant
        #   null - user has never tipped this person
        #   0.00 - user used to tip this person but now doesn't
        #   3.00 - user tips this person this amount
        if inquirer:
            if inquirer.id == self.id:
                my_tip = 'self'
            else:
                my_tip = inquirer.get_tip_to(self)['amount']
            output['my_tip'] = str(my_tip)

        # Key: elsewhere
        accounts = self.get_accounts_elsewhere()
        elsewhere = output['elsewhere'] = {}
        for platform, account in accounts.items():
            fields = ['id', 'user_id', 'user_name']
            elsewhere[platform] = {k: getattr(account, k, None) for k in fields}

        return output

    def path(self, path):
        return '/%s/%s' % (self.username, path)


class NeedConfirmation(Exception):
    """Represent the case where we need user confirmation during a merge.

    This is used in the workflow for merging one participant into another.

    """

    def __init__(self, a, c):
        self.other_is_a_real_participant = a
        self.we_already_have_that_kind_of_account = c
        self._all = (a, c)

    def __repr__(self):
        return "<NeedConfirmation: %r %r>" % self._all
    __str__ = __repr__

    def __eq__(self, other):
        return self._all == other._all

    def __ne__(self, other):
        return not self.__eq__(other)

    def __bool__(self):
        return any(self._all)
    __nonzero__ = __bool__
