from __future__ import print_function, unicode_literals

from datetime import timedelta
from decimal import Decimal, ROUND_DOWN
import pickle
from time import sleep
from urllib import quote
import uuid

from aspen.utils import utcnow
import balanced
from dependency_injection import resolve_dependencies
from markupsafe import escape as htmlescape
from postgres.orm import Model
from psycopg2 import IntegrityError

import liberapay
from liberapay.exceptions import (
    UsernameIsEmpty,
    UsernameTooLong,
    UsernameContainsInvalidCharacters,
    UsernameIsRestricted,
    UsernameAlreadyTaken,
    NoSelfTipping,
    NoTippee,
    BadAmount,
    UserDoesntAcceptTips,
    EmailAlreadyTaken,
    CannotRemovePrimaryEmail,
    EmailNotVerified,
    TooManyEmailAddresses,
)

from liberapay.models import add_event
from liberapay.models._mixin_team import MixinTeam
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.security.crypto import constant_time_compare
from liberapay.utils import i18n, is_card_expiring, emails, notifications


ASCII_ALLOWED_IN_USERNAME = set("0123456789"
                                "abcdefghijklmnopqrstuvwxyz"
                                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                "-_")

EMAIL_HASH_TIMEOUT = timedelta(hours=24)

USERNAME_MAX_SIZE = 32


class Participant(Model, MixinTeam):

    typname = 'participants'

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
    def make_stub(cls, cursor=None):
        """Return a new stub participant.
        """
        with cls.db.get_cursor(cursor) as c:
            return c.one("""
                INSERT INTO participants DEFAULT VALUES
                  RETURNING participants.*::participants
            """)

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
    def from_session_token(cls, token):
        """Return an existing participant based on session token.
        """
        participant = cls._from_thing("session_token", token)
        if participant and participant.session_expires < utcnow():
            participant = None

        return participant

    @classmethod
    def _from_thing(cls, thing, value):
        assert thing in ("id", "lower(username)", "session_token", "api_key")
        return cls.db.one("""

            SELECT participants.*::participants
              FROM participants
             WHERE {}=%s

        """.format(thing), (value,))


    # Session Management
    # ==================

    def update_session(self, new_token, expires):
        """Set ``session_token`` and ``session_expires``.

        :database: One UPDATE, one row

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

        :database: One UPDATE, one row

        """
        self.db.run( "UPDATE participants SET session_expires=%s "
                     "WHERE id=%s AND is_suspicious IS NOT true"
                   , (expires, self.id,)
                    )
        self.set_attributes(session_expires=expires)


    # Suspiciousness
    # ==============

    @property
    def is_whitelisted(self):
        return self.is_suspicious is False


    # Number
    # ======

    @property
    def IS_SINGULAR(self):
        return self.number == 'singular'

    @property
    def IS_PLURAL(self):
        return self.number == 'plural'

    def update_number(self, number):
        assert number in ('singular', 'plural')
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(action='set', id=self.id, values=dict(number=number)))
            self.remove_all_members(c)
            c.execute("""
                UPDATE participants
                   SET number=%s
                     , anonymous_receiving=false
                 WHERE id=%s
            """, (number, self.id))
        self.set_attributes(number=number)


    # Statement
    # =========

    def get_statement(self, langs):
        """Get the participant's statement in the language that best matches
        the list provided.
        """
        return self.db.one("""
            SELECT content, lang
              FROM statements
              JOIN enumerate(%(langs)s) langs ON langs.value = statements.lang
             WHERE participant=%(id)s
          ORDER BY langs.rank
             LIMIT 1
        """, dict(id=self.id, langs=langs), default=(None, None))

    def get_statement_langs(self):
        return self.db.all("SELECT lang FROM statements WHERE participant=%s",
                           (self.id,))

    def upsert_statement(self, lang, statement):
        if not statement:
            self.db.run("DELETE FROM statements WHERE participant=%s AND lang=%s",
                        (self.id, lang))
            return
        r = self.db.one("""
            UPDATE statements
               SET content=%s
             WHERE participant=%s
               AND lang=%s
         RETURNING true
        """, (statement, self.id, lang))
        if not r:
            search_conf = i18n.SEARCH_CONFS.get(lang, 'simple')
            try:
                self.db.run("""
                    INSERT INTO statements
                                (lang, content, participant, search_conf)
                         VALUES (%s, %s, %s, %s)
                """, (lang, statement, self.id, search_conf))
            except IntegrityError:
                return self.upsert_statement(lang, statement)


    # Pricing
    # =======

    @property
    def usage(self):
        return max(self.giving + self.pledging, self.receiving)

    @property
    def suggested_payment(self):
        return (self.usage * Decimal('0.05')).quantize(Decimal('.01'))


    # API Key
    # =======

    def recreate_api_key(self):
        api_key = self._generate_api_key()
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(action='set', id=self.id, values=dict(api_key=api_key)))
            api_key = c.one("""
                UPDATE participants
                   SET api_key=%s
                 WHERE id=%s
             RETURNING api_key
            """, (api_key, self.id))
        self.set_attributes(api_key=api_key)
        return api_key

    def _generate_api_key(self):
        return str(uuid.uuid4())


    # Stubs
    # =====

    def resolve_stub(self):
        rec = self.db.one("""
            SELECT platform, user_name
              FROM elsewhere
             WHERE participant = %s
        """, (self.id,))
        return rec and '/on/%s/%s/' % (rec.platform, rec.user_name)


    # Archiving/Closing
    # =================

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

    def archive(self, cursor):
        """Given a cursor, use it to archive ourself.
        """
        self.final_check(cursor)
        self.clear_personal_information(cursor)
        self.update_status('archived', cursor)

    class UnknownDisbursementStrategy(Exception): pass

    def close(self, disbursement_strategy):
        """Close the participant's account.
        """
        with self.db.get_cursor() as cursor:
            if disbursement_strategy == None:
                pass  # No balance, supposedly. final_check will make sure.
            elif disbursement_strategy == 'bank':
                self.withdraw_balance_to_bank_account()
            elif disbursement_strategy == 'downstream':
                # This in particular needs to come before clear_tips_giving.
                self.distribute_balance_as_final_gift(cursor)
            else:
                raise self.UnknownDisbursementStrategy

            self.clear_tips_giving(cursor)
            self.clear_tips_receiving(cursor)
            self.clear_personal_information(cursor)
            self.final_check(cursor)
            self.update_status('closed', cursor)

    class BankWithdrawalFailed(Exception): pass

    def withdraw_balance_to_bank_account(self):
        from liberapay.billing.exchanges import ach_credit
        error = ach_credit( self.db
                          , self
                          , Decimal('0.00') # don't withhold anything
                          , Decimal('0.00') # send it all
                           )
        if error:
            raise self.BankWithdrawalFailed(error)

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

        for tippee, amount in transfers:
            assert amount > 0
            balance = cursor.one("""
                UPDATE participants
                   SET balance = balance - %s
                 WHERE id = %s
             RETURNING balance
            """, (amount, self.id))
            assert balance >= 0  # sanity check
            cursor.run( "UPDATE participants SET balance=balance + %s WHERE id=%s"
                      , (amount, tippee)
                       )
            cursor.run( "INSERT INTO transfers (tipper, tippee, amount, context) "
                        "VALUES (%s, %s, %s, 'final-gift')"
                      , (self.id, tippee, amount)
                       )

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
            t.set_take_for(self, Decimal(0), self, cursor)

    def clear_personal_information(self, cursor):
        """Clear personal information such as statements and goal.
        """
        if self.IS_PLURAL:
            self.remove_all_members(cursor)
        self.clear_takes(cursor)
        r = cursor.one("""

            INSERT INTO community_members (slug, participant, ctime, name, is_member) (
                SELECT slug, participant, ctime, name, false
                  FROM community_members
                 WHERE participant=%(participant_id)s
                   AND is_member IS true
            );

            DELETE FROM emails WHERE participant=%(participant_id)s;
            DELETE FROM statements WHERE participant=%(participant_id)s;

            UPDATE participants
               SET goal=NULL
                 , anonymous_giving=False
                 , anonymous_receiving=False
                 , avatar_url=NULL
                 , email_address=NULL
                 , session_token=NULL
                 , session_expires=now()
                 , giving=0
                 , pledging=0
                 , receiving=0
                 , npatrons=0
             WHERE id=%(participant_id)s
         RETURNING *;

        """, dict(participant_id=self.id))
        self.set_attributes(**r._asdict())

    @property
    def closed_time(self):
        return self.db.one("""
            SELECT ts AT TIME ZONE 'UTC'
              FROM events
             WHERE payload->>'id'=%s
               AND payload->>'action'='set'
               AND payload->'values'->>'status'='closed'
          ORDER BY ts DESC
             LIMIT 1
        """, (str(self.id),))


    # Emails
    # ======

    def add_email(self, email):
        """
            This is called when
            1) Adding a new email address
            2) Resending the verification email for an unverified email address

            Returns the number of emails sent.
        """

        # Check that this address isn't already verified
        owner = self.db.one("""
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
        verification_start = utcnow()
        try:
            with self.db.get_cursor() as c:
                add_event(c, 'participant', dict(id=self.id, action='add', values=dict(email=email)))
                c.run("""
                    INSERT INTO emails
                                (address, nonce, verification_start, participant)
                         VALUES (%s, %s, %s, %s)
                """, (email, nonce, verification_start, self.id))
        except IntegrityError:
            nonce = self.db.one("""
                UPDATE emails
                   SET verification_start=%s
                 WHERE participant=%s
                   AND address=%s
                   AND verified IS NULL
             RETURNING nonce
            """, (verification_start, self.id, email))
            if not nonce:
                return self.add_email(email)

        scheme = liberapay.canonical_scheme
        host = liberapay.canonical_host
        username = self.username
        quoted_email = quote(email)
        link = "{scheme}://{host}/{username}/emails/verify.html?email={quoted_email}&nonce={nonce}"
        r = self.send_email('verification',
                        email=email,
                        link=link.format(**locals()),
                        include_unsubscribe=False)
        assert r == 1 # Make sure the verification email was sent
        if self.email_address:
            self.send_email('verification_notice',
                            new_email=email,
                            include_unsubscribe=False)
            return 2
        return 1

    def update_email(self, email):
        if not getattr(self.get_email(email), 'verified', False):
            raise EmailNotVerified(email)
        id = self.id
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(id=self.id, action='set', values=dict(primary_email=email)))
            c.run("""
                UPDATE participants
                   SET email_address=%(email)s
                 WHERE id=%(id)s
            """, locals())
        self.set_attributes(email_address=email)

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
        if (utcnow() - r.verification_start) > EMAIL_HASH_TIMEOUT:
            return emails.VERIFICATION_EXPIRED
        try:
            self.db.run("""
                UPDATE emails
                   SET verified=true, verification_end=now(), nonce=NULL
                 WHERE participant=%s
                   AND address=%s
                   AND verified IS NULL
            """, (self.id, email))
        except IntegrityError:
            return emails.VERIFICATION_STYMIED

        if not self.email_address:
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
        if address == self.email_address:
            raise CannotRemovePrimaryEmail()
        with self.db.get_cursor() as c:
            add_event(c, 'participant', dict(id=self.id, action='remove', values=dict(email=address)))
            c.run("DELETE FROM emails WHERE participant=%s AND address=%s",
                  (self.id, address))

    def send_email(self, spt_name, **context):
        context['participant'] = self
        context['username'] = self.username
        context['button_style'] = (
            "color: #fff; text-decoration:none; display:inline-block; "
            "padding: 0 15px; background: #396; white-space: nowrap; "
            "font: normal 14px/40px Arial, sans-serif; border-radius: 3px"
        )
        context.setdefault('include_unsubscribe', True)
        email = context.setdefault('email', self.email_address)
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
        message['subject'] = spt['subject'].render(context)
        message['html'] = render('text/html', context_html)
        message['text'] = render('text/plain', context)

        self._mailer.messages.send(message=message)
        return 1 # Sent

    def notify_patrons(self, elsewhere, tips=None):
        tips = self.get_tips_receiving() if tips is None else tips
        for t in tips:
            p = Participant.from_id(t.tipper)
            if p.email_address and p.notify_on_opt_in:
                p.queue_email(
                    'notify_patron',
                    user_name=elsewhere.user_name,
                    platform=elsewhere.platform_data.display_name,
                    amount=t.amount,
                    profile_url=elsewhere.liberapay_url,
                )

    def queue_email(self, spt_name, **context):
        self.db.run("""
            INSERT INTO email_queue
                        (participant, spt_name, context)
                 VALUES (%s, %s, %s)
        """, (self.id, spt_name, pickle.dumps(context)))

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

    def add_notification(self, name):
        id = self.id
        r = self.db.one("""
            UPDATE participants
               SET notifications = array_append(notifications, %(name)s)
             WHERE id = %(id)s
               AND NOT %(name)s = ANY(notifications);

            SELECT notifications
              FROM participants
             WHERE id = %(id)s;
        """, locals())
        self.set_attributes(notifications=r)

    def add_signin_notifications(self):
        if not self.get_emails():
            self.add_notification('email_missing')
        if self.get_bank_account_error():
            self.add_notification('ba_withdrawal_failed')
        if self.get_credit_card_error():
            self.add_notification('credit_card_failed')
        elif self.credit_card_expiring():
            self.add_notification('credit_card_expires')

    def credit_card_expiring(self):
        route = ExchangeRoute.from_network(self, 'balanced-cc')
        if not route:
            return
        card = balanced.Card.fetch(route.address)
        year, month = card.expiration_year, card.expiration_month
        if not (year and month):
            return False
        return is_card_expiring(int(year), int(month))

    def remove_notification(self, name):
        id = self.id
        r = self.db.one("""
            UPDATE participants
               SET notifications = array_remove(notifications, %(name)s)
             WHERE id = %(id)s
         RETURNING notifications
        """, locals())
        self.set_attributes(notifications=r)

    def render_notifications(self, state):
        r = []
        escape = state['escape']
        state['escape'] = lambda a: a
        for name in self.notifications:
            try:
                f = getattr(notifications, name)
                typ, msg = f(*resolve_dependencies(f, state).as_args)
                r.append(dict(jsonml=msg, name=name, type=typ))
            except Exception as e:
                self._tell_sentry(e, state)
        state['escape'] = escape
        return r


    # Exchange-related stuff
    # ======================

    def get_bank_account_error(self):
        return getattr(ExchangeRoute.from_network(self, 'balanced-ba'), 'error', None)

    def get_credit_card_error(self):
        return getattr(ExchangeRoute.from_network(self, 'balanced-cc'), 'error', None)

    def get_cryptocoin_addresses(self):
        routes = self.db.all("""
            SELECT network, address
              FROM current_exchange_routes r
             WHERE participant = %s
               AND network = 'bitcoin'
               AND error <> 'invalidated'
        """, (self.id,))
        return {r.network: r.address for r in routes}


    # Random Junk
    # ===========

    @property
    def profile_url(self):
        scheme = liberapay.canonical_scheme
        host = liberapay.canonical_host
        username = self.username
        return '{scheme}://{host}/{username}/'.format(**locals())

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


    def insert_into_communities(self, is_member, name, slug):
        participant_id = self.id
        self.db.run("""

            INSERT INTO community_members
                        (ctime, name, slug, participant, is_member)
                 VALUES ( COALESCE (( SELECT ctime
                                        FROM community_members
                                       WHERE participant=%(participant_id)s
                                         AND slug=%(slug)s
                                       LIMIT 1
                                      ), CURRENT_TIMESTAMP)
                        , %(name)s, %(slug)s, %(participant_id)s, %(is_member)s
                         )

        """, locals())


    def change_username(self, suggested):
        """Raise Response or return None.

        Usernames are limited to alphanumeric characters, plus ".,-_:@ ",
        and can only be 32 characters long.

        """
        # TODO: reconsider allowing unicode usernames
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
            try:
                # Will raise IntegrityError if the desired username is taken.
                with self.db.get_cursor(back_as=tuple) as c:
                    add_event(c, 'participant', dict(id=self.id, action='set', values=dict(username=suggested)))
                    actual = c.one("""
                        UPDATE participants
                           SET username=%s
                         WHERE id=%s
                     RETURNING username, lower(username)
                    """, (suggested, self.id))
            except IntegrityError:
                raise UsernameAlreadyTaken(suggested)

            assert (suggested, lowercased) == actual # sanity check
            self.set_attributes(username=suggested)

        return suggested

    def update_avatar(self):
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
            tmp = goal if goal is None else unicode(goal)
            add_event(c, 'participant', dict(id=self.id, action='set', values=dict(goal=tmp)))
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
            add_event(c, 'participant', dict(id=self.id, action='set', values=dict(status=status)))
            if status == 'closed':
                self.update_goal(-1, c)
            elif status == 'active':
                self.update_goal(None, c)

    def update_giving_and_tippees(self):
        with self.db.get_cursor() as cursor:
            updated_tips = self.update_giving(cursor)
            for tip in updated_tips:
                Participant.from_id(tip.tippee).update_receiving(cursor)

    def update_giving(self, cursor=None):
        # Update is_funded on tips
        if self.get_credit_card_error() == '':
            updated = (cursor or self.db).all("""
                UPDATE current_tips
                   SET is_funded = true
                 WHERE tipper = %s
                   AND is_funded IS NOT true
             RETURNING *
            """, (self.id,))
        else:
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

        # Update giving and pledging on participant
        giving, pledging = (cursor or self.db).one("""
            WITH our_tips AS (
                     SELECT amount, p2.status
                       FROM current_tips
                       JOIN participants p2 ON p2.id = tippee
                      WHERE tipper = %(id)s
                        AND p2.is_suspicious IS NOT true
                        AND amount > 0
                        AND is_funded
                 )
            UPDATE participants p
               SET giving = COALESCE((
                       SELECT sum(amount)
                         FROM our_tips
                        WHERE status = 'active'
                   ), 0)
                 , pledging = COALESCE((
                       SELECT sum(amount)
                         FROM our_tips
                        WHERE status = 'stub'
                   ), 0)
             WHERE p.id = %(id)s
         RETURNING giving, pledging
        """, dict(id=self.id))
        self.set_attributes(giving=giving, pledging=pledging)

        return updated

    def update_receiving(self, cursor=None):
        if self.IS_PLURAL:
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
        if self.IS_PLURAL:
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
        if amount != 0 and amount < liberapay.MIN_TIP or amount > liberapay.MAX_TIP:
            raise BadAmount

        if not tippee.accepts_tips and amount != 0:
            raise UserDoesntAcceptTips

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

        """
        args = dict(tipper=self.id, tippee=tippee.id, amount=amount)
        t = (cursor or self.db).one(NEW_TIP, args)

        if update_self:
            # Update giving/pledging amount of tipper
            self.update_giving(cursor)
        if update_tippee:
            # Update receiving amount of tippee
            tippee.update_receiving(cursor)

        return t._asdict()


    def get_tip_to(self, tippee):
        """Given a participant (or their id), returns a dict.
        """
        default = dict(amount=Decimal('0.00'), is_funded=False)
        if isinstance(tippee, Participant):
            tippee = tippee.id
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
                     , p.number
                  FROM tips t
                  JOIN participants p ON p.id = t.tippee
                 WHERE tipper = %s
                   AND p.is_suspicious IS NOT true
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
                   AND p.is_suspicious IS NOT true
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


    def get_elsewhere_logins(self, cursor):
        """Return the list of (platform, user_id) tuples that the participant
        can log in with.
        """
        return cursor.all("""
            SELECT platform, user_id
              FROM elsewhere
             WHERE participant=%s
               AND platform IN %s
               AND NOT is_team
        """, (self.id, AccountElsewhere.signin_platforms_names))


    def get_balanced_account(self):
        """Fetch or create the balanced account for this participant.
        """
        if not self.balanced_customer_href:
            customer = balanced.Customer(meta={
                'username': self.username,
                'participant_id': self.id,
            }).save()
            r = self.db.one("""
                UPDATE participants
                   SET balanced_customer_href=%s
                 WHERE id=%s
                   AND balanced_customer_href IS NULL
             RETURNING id
            """, (customer.href, self.id))
            if not r:
                return self.get_balanced_account()
        else:
            customer = balanced.Customer.fetch(self.balanced_customer_href)
        return customer


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
        confirmation. If it was the last account elsewhere connected to the old
        Liberapay account, then we absorb the old Liberapay account into the new one,
        effectively archiving the old account.

        Here's what absorbing means:

            - consolidated tips to and fro are set up for the new participant

                Amounts are summed, so if alice tips bob $1 and carl $1, and
                then bob absorbs carl, then alice tips bob $2(!) and carl $0.

                And if bob tips alice $1 and carl tips alice $1, and then bob
                absorbs carl, then bob tips alice $2(!) and carl tips alice $0.

                The ctime of each new consolidated tip is the older of the two
                tips that are being consolidated.

                If alice tips bob $1, and alice absorbs bob, then alice tips
                bob $0.

                If alice tips bob $1, and bob absorbs alice, then alice tips
                bob $0.

            - all tips to and from the other participant are set to zero
            - the absorbed username is released for reuse
            - the absorption is recorded in an absorptions table

        This is done in one transaction.
        """

        if isinstance(account, AccountElsewhere):
            platform, user_id = account.platform, account.user_id
        else:
            platform, user_id = map(str, account)

        CREATE_TEMP_TABLE_FOR_UNIQUE_TIPS = """

        CREATE TEMP TABLE __temp_unique_tips ON COMMIT drop AS

            -- Get all the latest tips from everyone to everyone.

            SELECT ctime, tipper, tippee, amount, is_funded
              FROM current_tips
             WHERE amount > 0;

        """

        CONSOLIDATE_TIPS_RECEIVING = """

            -- Create a new set of tips, one for each current tip *to* either
            -- the dead or the live account. If a user was tipping both the
            -- dead and the live account, then we create one new combined tip
            -- to the live account (via the GROUP BY and sum()).

            INSERT INTO tips (ctime, tipper, tippee, amount, is_funded)

                 SELECT min(ctime), tipper, %(live)s AS tippee, sum(amount), bool_and(is_funded)

                   FROM __temp_unique_tips

                  WHERE (tippee = %(dead)s OR tippee = %(live)s)
                        -- Include tips *to* either the dead or live account.

                AND NOT (tipper = %(dead)s OR tipper = %(live)s)
                        -- Don't include tips *from* the dead or live account,
                        -- lest we convert cross-tipping to self-tipping.

               GROUP BY tipper

        """

        CONSOLIDATE_TIPS_GIVING = """

            -- Create a new set of tips, one for each current tip *from* either
            -- the dead or the live account. If both the dead and the live
            -- account were tipping a given user, then we create one new
            -- combined tip from the live account (via the GROUP BY and sum()).

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), %(live)s AS tipper, tippee, sum(amount)

                   FROM __temp_unique_tips

                  WHERE (tipper = %(dead)s OR tipper = %(live)s)
                        -- Include tips *from* either the dead or live account.

                AND NOT (tippee = %(dead)s OR tippee = %(live)s)
                        -- Don't include tips *to* the dead or live account,
                        -- lest we convert cross-tipping to self-tipping.

               GROUP BY tippee

        """

        ZERO_OUT_OLD_TIPS_RECEIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM __temp_unique_tips
                 WHERE tippee=%s

        """

        ZERO_OUT_OLD_TIPS_GIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM __temp_unique_tips
                 WHERE tipper=%s

        """

        TRANSFER_BALANCE_1 = """

            UPDATE participants
               SET balance = (balance - %(balance)s)
             WHERE id=%(dead)s
         RETURNING balance;

        """

        TRANSFER_BALANCE_2 = """

            INSERT INTO transfers (tipper, tippee, amount, context)
            SELECT %(dead)s, %(live)s, %(balance)s, 'take-over'
             WHERE %(balance)s > 0;

            UPDATE participants
               SET balance = (balance + %(balance)s)
             WHERE id=%(live)s
         RETURNING balance;

        """

        MERGE_EMAIL_ADDRESSES = """

            WITH emails_to_keep AS (
                     SELECT DISTINCT ON (address) id
                       FROM emails
                      WHERE participant IN (%(dead)s, %(live)s)
                   ORDER BY address, verification_end, verification_start DESC
                 )
            DELETE FROM emails
             WHERE participant IN (%(dead)s, %(live)s)
               AND id NOT IN (SELECT id FROM emails_to_keep);

            UPDATE emails
               SET participant = %(live)s
             WHERE participant = %(dead)s;

        """

        new_balance = None

        with self.db.get_cursor() as cursor:

            # Load the existing connection.
            # =============================
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
            # We need confirmation in whatever combination of the following
            # three cases:
            #
            #   - the other participant is not a stub; we are taking the
            #       account elsewhere away from another viable participant
            #
            #   - the other participant has no other accounts elsewhere; taking
            #       away the account elsewhere will leave the other participant
            #       without any means of logging in, and it will be archived
            #       and its tips absorbed by us
            #
            #   - we already have an account elsewhere connected from the given
            #       platform, and it will be handed off to a new stub
            #       participant

            # other_is_a_real_participant
            other_is_a_real_participant = other.status != 'stub'

            # this_is_others_last_login_account
            nelsewhere = len(other.get_elsewhere_logins(cursor))
            this_is_others_last_login_account = (nelsewhere <= 1)

            # we_already_have_that_kind_of_account
            we_already_have_that_kind_of_account = cursor.one("""
                SELECT true
                  FROM elsewhere
                 WHERE participant=%s AND platform=%s
            """, (self.id, platform), default=False)

            if elsewhere.is_team and we_already_have_that_kind_of_account:
                if len(self.get_accounts_elsewhere()) == 1:
                    raise TeamCantBeOnlyAuth

            need_confirmation = NeedConfirmation(
                other_is_a_real_participant,
                this_is_others_last_login_account,
                we_already_have_that_kind_of_account,
            )
            if need_confirmation and not have_confirmation:
                raise need_confirmation


            # Move any old account out of the way.
            # ====================================

            if we_already_have_that_kind_of_account:
                new_stub = Participant.make_stub(cursor)
                cursor.run( "UPDATE elsewhere SET participant=%s "
                            "WHERE platform=%s AND participant=%s"
                          , (new_stub.id, platform, self.id)
                           )


            # Do the deal.
            # ============
            # If other_is_not_a_stub, then other will have the account
            # elsewhere taken away from them with this call.

            cursor.run( "UPDATE elsewhere SET participant=%s "
                        "WHERE platform=%s AND user_id=%s"
                      , (self.id, platform, user_id)
                       )


            # Fold the old participant into the new as appropriate.
            # =====================================================
            # We want to do this whether or not other is a stub participant.

            if this_is_others_last_login_account:

                other.clear_takes(cursor)

                # Take over tips
                x, y = self.id, other.id
                cursor.run(CREATE_TEMP_TABLE_FOR_UNIQUE_TIPS)
                cursor.run(CONSOLIDATE_TIPS_RECEIVING, dict(live=x, dead=y))
                cursor.run(CONSOLIDATE_TIPS_GIVING, dict(live=x, dead=y))
                cursor.run(ZERO_OUT_OLD_TIPS_RECEIVING, (other.id,))
                cursor.run(ZERO_OUT_OLD_TIPS_GIVING, (other.id,))

                # Take over balance
                other_balance = other.balance
                args = dict(live=x, dead=y, balance=other_balance)
                archive_balance = cursor.one(TRANSFER_BALANCE_1, args)
                other.set_attributes(balance=archive_balance)
                new_balance = cursor.one(TRANSFER_BALANCE_2, args)

                # Take over email addresses
                cursor.run(MERGE_EMAIL_ADDRESSES, dict(live=x, dead=y))

                # Disconnect any remaining elsewhere account
                cursor.run("DELETE FROM elsewhere WHERE participant=%s", (y,))

                # Archive the old participant
                other.archive(cursor)

                # Record the absorption
                cursor.run("""
                    INSERT INTO absorptions
                                (absorbed_was, absorbed_by, archived_as)
                         VALUES (%s, %s, %s)
                """, (other.username, self.id, other.id))

        if new_balance is not None:
            self.set_attributes(balance=new_balance)

        if old_tips:
            self.notify_patrons(elsewhere, tips=old_tips)

        self.update_avatar()

        # Note: the order matters here, receiving needs to be updated before giving
        self.update_receiving()
        self.update_giving()

    @property
    def absorbed_by(self):
        return self.db.one("""
            SELECT p.username
              FROM absorptions a
              JOIN participants p ON p.id = a.absorbed_by
             WHERE archived_as = %s
        """, (self.id,), default=Exception)

    def delete_elsewhere(self, platform, user_id):
        """Deletes account elsewhere unless the user would not be able
        to log in anymore.
        """
        user_id = unicode(user_id)
        with self.db.get_cursor() as c:
            accounts = self.get_elsewhere_logins(c)
            assert len(accounts) > 0
            if len(accounts) == 1 and accounts[0] == (platform, user_id):
                raise LastElsewhere()
            c.one("""
                DELETE FROM elsewhere
                WHERE participant=%s
                AND platform=%s
                AND user_id=%s
                RETURNING participant
            """, (self.id, platform, user_id), default=NonexistingElsewhere)
            add_event(c, 'participant', dict(id=self.id, action='disconnect', values=dict(platform=platform, user_id=user_id)))
        self.update_avatar()

    def to_dict(self, details=False, inquirer=None):
        output = { 'id': self.id
                 , 'username': self.username
                 , 'avatar': self.avatar_url
                 , 'number': self.number
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
        if not self.anonymous_receiving:
            receiving = str(self.receiving)
        else:
            receiving = None
        output['receiving'] = receiving

        # Key: giving
        # Values:
        #   null - user is giving anonymously
        #   3.00 - user gives this amount in tips
        if not self.anonymous_giving:
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

        # Key: cryptocoins
        output['cryptocoins'] = self.get_cryptocoin_addresses()

        return output


class NeedConfirmation(Exception):
    """Represent the case where we need user confirmation during a merge.

    This is used in the workflow for merging one participant into another.

    """

    def __init__(self, a, b, c):
        self.other_is_a_real_participant = a
        self.this_is_others_last_login_account = b
        self.we_already_have_that_kind_of_account = c
        self._all = (a, b, c)

    def __repr__(self):
        return "<NeedConfirmation: %r %r %r>" % self._all
    __str__ = __repr__

    def __eq__(self, other):
        return self._all == other._all

    def __ne__(self, other):
        return not self.__eq__(other)

    def __nonzero__(self):
        # bool(need_confirmation)
        A, B, C = self._all
        return A or C

class LastElsewhere(Exception): pass

class NonexistingElsewhere(Exception): pass

class TeamCantBeOnlyAuth(Exception): pass
