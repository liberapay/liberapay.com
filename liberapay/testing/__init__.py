"""Helpers for testing.
"""

from contextlib import contextmanager
from io import BytesIO
import json
from os.path import dirname, join, realpath
import unittest

import html5lib
from pando.testing.client import Client
from pando.utils import utcnow
from psycopg2 import IntegrityError, InternalError
import stripe

from liberapay.constants import SESSION
from liberapay.elsewhere._base import UserInfo
from liberapay.exceptions import MissingPaymentAccount
from liberapay.i18n.currencies import Money
from liberapay.main import website
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.payin.common import (
    adjust_payin_transfers, prepare_payin, resolve_tip,
    update_payin, update_payin_transfer,
)
from liberapay.security.csrf import CSRF_TOKEN
from liberapay.testing.vcr import use_cassette


TOP = realpath(join(dirname(dirname(__file__)), '..'))
WWW_ROOT = str(realpath(join(TOP, 'www')))
PROJECT_ROOT = str(TOP)


def EUR(amount):
    return Money(amount, 'EUR')


def KRW(amount):
    return Money(amount, 'KRW')


def JPY(amount):
    return Money(amount, 'JPY')


def USD(amount):
    return Money(amount, 'USD')


html5parser = html5lib.HTMLParser(strict=True)


class ClientWithAuth(Client):

    def __init__(self, *a, **kw):
        Client.__init__(self, *a, **kw)
        Client.website = website

    def build_wsgi_environ(self, method, *a, **kw):
        """Extend base class to support authenticating as a certain user.
        """

        # csrf - for both anon and authenticated
        csrf_token = kw.get('csrf_token', 'ThisIsATokenThatIsThirtyTwoBytes')
        if csrf_token:
            cookies = kw.setdefault('cookies', {})
            cookies[CSRF_TOKEN] = csrf_token
            kw['HTTP_X-CSRF-TOKEN'] = csrf_token

        # user authentication
        auth_as = kw.pop('auth_as', None)
        if auth_as:
            cookies = kw.setdefault('cookies', {})
            sess = auth_as.session
            if not sess:
                sess = auth_as.session = auth_as.start_session()
            cookies[SESSION] = '%i:%i:%s' % (auth_as.id, sess.id, sess.secret)

        environ = super().build_wsgi_environ(method, *a, **kw)
        if method not in ('POST', 'PUT'):
            environ.pop(b'CONTENT_TYPE', None)
            environ[b'wsgi.input'] = BytesIO()
        return environ

    def hit(self, method, url, *a, **kw):
        if kw.pop('xhr', False):
            kw['HTTP_X_REQUESTED_WITH'] = b'XMLHttpRequest'

        # prevent tell_sentry from reraising errors
        sentry_reraise = kw.pop('sentry_reraise', True)
        env = self.website.env
        old_reraise = env.sentry_reraise
        if sentry_reraise != old_reraise:
            env.sentry_reraise = sentry_reraise

        want = kw.get('want', 'response')
        try:
            wanted = super().hit(method, url, *a, **kw)
            r = None
            if want == 'response':
                r = wanted
            elif want == 'state':
                r = wanted.get('response')
            if not r or not r.body:
                return wanted
            # Attempt to validate the response body, unless asked not to
            if not kw.pop('parse_output', True):
                return wanted
            r_type = r.headers[b'Content-Type']
            try:
                if r_type.startswith(b'text/html'):
                    r.html_tree = html5parser.parse(r.text)
                elif r_type.startswith(b'application/json'):
                    json.loads(r.body)
                elif r_type.startswith(b'application/javascript'):
                    pass
                elif r_type.startswith(b'text/css'):
                    pass
                elif r_type.startswith(b'image/'):
                    pass
                elif r_type.startswith(b'text/'):
                    pass
                else:
                    raise ValueError(f"unknown response media type {r_type!r}")
            except Exception as e:
                print(r.text)
                raise Exception(
                    f"parsing body of {r.code} response to `{method} {url}` failed:"
                    f"\n{str(e)}"
                )
            return wanted
        finally:
            env.sentry_reraise = old_reraise


class Harness(unittest.TestCase):

    client = ClientWithAuth(www_root=WWW_ROOT, project_root=PROJECT_ROOT)
    db = client.website.db
    platforms = client.website.platforms
    website = client.website
    tablenames = db.all("""
        SELECT tablename
          FROM pg_tables
         WHERE schemaname='public'
           AND tablename NOT IN ('db_meta', 'app_conf', 'payday_transfers', 'currency_exchange_rates')
    """)


    @classmethod
    def setUpClass(cls):
        cls_name = cls.__name__
        if cls_name[4:5].isupper():
            f = lambda x: x - 97 if x >= 97 else x
            cls_id = sum(f(ord(c)) << (i*5) for i, c in enumerate(cls_name[4:10].lower()))
        else:
            cls_id = 1
        cls.db.run("ALTER SEQUENCE exchanges_id_seq RESTART WITH %s", (cls_id,))
        cls.db.run("ALTER SEQUENCE transfers_id_seq RESTART WITH %s", (cls_id,))
        cls.setUpVCR()
        cls.make_table_read_only('currency_exchange_rates')


    @classmethod
    def setUpVCR(cls):
        """Set up VCR.

        We use the VCR library to freeze API calls. Frozen calls are stored in
        tests/fixtures/ for your convenience (otherwise your first test run
        would take fooooorrr eeeevvveeerrrr). If you find that an API call has
        drifted from our frozen version of it, simply remove that fixture file
        and rerun. The VCR library should recreate the fixture with the new
        information, and you can commit that with your updated tests.

        """
        cls.vcr_cassette = use_cassette(cls.__name__)
        cls.vcr_cassette.__enter__()


    @classmethod
    def tearDownClass(cls):
        cls.vcr_cassette.__exit__(None, None, None)


    def setUp(self):
        self.clear_tables()


    def tearDown(self):
        self.clear_tables()


    def clear_tables(self):
        tried = set()
        tablenames = self.tablenames[:]
        while tablenames:
            tablename = tablenames.pop()
            try:
                # I tried TRUNCATE but that was way slower for me.
                self.db.run("DELETE FROM %s CASCADE" % tablename)
            except (IntegrityError, InternalError):
                if not tablenames:
                    raise
                tablenames.insert(0, tablename)
                if tuple(tablenames) in tried:
                    # Stop infinite loop
                    raise
                self.tablenames.remove(tablename)
                self.tablenames.insert(0, tablename)
                tried.add(tuple(tablenames))
        self.db.run("ALTER SEQUENCE participants_id_seq RESTART WITH 1")
        self.db.run("ALTER SEQUENCE paydays_id_seq RESTART WITH 1")


    @classmethod
    def make_table_read_only(cls, table_name):
        cls.db.run("""
            CREATE OR REPLACE FUNCTION prevent_changes() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION
                        'The % table is read-only by default during tests.',
                        TG_TABLE_NAME;
                END;
            $$ LANGUAGE plpgsql;

            CREATE OR REPLACE TRIGGER prevent_changes_to_{0}
                BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON {0}
                FOR EACH STATEMENT EXECUTE PROCEDURE prevent_changes();
        """.format(table_name))


    @contextmanager
    def allow_changes_to(self, table_name):
        self.db.run("DROP TRIGGER prevent_changes_to_{0} ON {0}".format(table_name))
        try:
            yield
        finally:
            self.make_table_read_only(table_name)


    def make_elsewhere(self, platform, user_id, user_name, domain='', **kw):
        info = UserInfo(platform=platform, user_id=str(user_id),
                        user_name=user_name, domain=domain, **kw)
        return AccountElsewhere.upsert(info)


    def make_participant(self, username, **kw):
        platform = kw.pop('elsewhere', 'github')
        domain = kw.pop('domain', '')
        kw.setdefault('kind', 'individual')
        kw.setdefault('status', 'active')
        if username:
            kw['username'] = username
        if 'join_time' not in kw:
            kw['join_time'] = utcnow()
        kw.setdefault('email_lang', 'en')
        kw.setdefault('main_currency', 'EUR')
        kw.setdefault('accepted_currencies', kw['main_currency'])

        cols, vals = zip(*kw.items())
        cols = ', '.join(cols)
        placeholders = ', '.join(['%s']*len(vals))
        participant = self.db.one("""
            INSERT INTO participants
                        ({0})
                 VALUES ({1})
              RETURNING participants.*::participants
        """.format(cols, placeholders), vals)

        if platform:
            self.db.run("""
                INSERT INTO elsewhere
                            (platform, user_id, user_name, participant, domain)
                     VALUES (%s,%s,%s,%s,%s)
            """, (platform, participant.id, username, participant.id, domain))

        email = kw.get('email', participant.username + '@liberapay.com')
        if email:
            self.db.run("""
                INSERT INTO emails
                            (participant, address, verified, verified_time)
                     VALUES (%s, %s, true, now())
            """, (participant.id, email))

        return participant


    def make_stub(self, **kw):
        return Participant.make_stub(**kw)


    def fetch_payday(self):
        return self.db.one("SELECT * FROM paydays", back_as=dict)


    def make_payin_and_transfer(
        self, route, tippee, amount,
        status='succeeded', error=None, payer_country=None, fee=None,
        remote_id='fake', pt_extra={},
    ):
        payin, payin_transfers = self.make_payin_and_transfers(
            route, amount, [(tippee, amount - (fee or 0), pt_extra)],
            status=status, error=error, payer_country=payer_country, fee=fee,
            remote_id=remote_id,
        )
        if len(payin_transfers) == 1:
            return payin, payin_transfers[0]
        else:
            return payin, payin_transfers

    def make_payin_and_transfers(
        self, route, amount, transfers,
        status='succeeded', error=None, payer_country=None, fee=None,
        remote_id='fake',
    ):
        payer = route.participant
        provider = route.network.split('-', 1)[0]
        proto_transfers = []
        net_amount = 0
        sepa_only = len(transfers) > 1
        for tippee, pt_amount, opt in transfers:
            net_amount += pt_amount
            tip = opt.get('tip')
            if tip:
                assert tip.tipper == payer.id
                assert tip.tippee == tippee.id
            else:
                tip = self.db.one("""
                    SELECT *
                      FROM current_tips
                     WHERE tipper = %s
                       AND tippee = %s
                """, (payer.id, tippee.id))
                assert tip
            for i in range(100):
                try:
                    proto_transfers.extend(resolve_tip(
                        self.db, tip, tippee, provider, payer, payer_country, pt_amount,
                        sepa_only=sepa_only,
                    ))
                except MissingPaymentAccount as e:
                    if i > 95:
                        # Infinite loop?
                        raise
                    recipient = e.args[0]
                    if recipient.kind == 'group':
                        raise
                    self.add_payment_account(recipient, provider)
                else:
                    break
        payin, payin_transfers = prepare_payin(self.db, payer, amount, route, proto_transfers)
        del proto_transfers
        payin = update_payin(self.db, payin.id, remote_id, status, error, fee=fee)
        if len(payin_transfers) > 1:
            adjust_payin_transfers(self.db, payin, net_amount)
        else:
            pt = payin_transfers[0]
            # Call `update_payin_transfer` twice to uncover bugs
            pt = update_payin_transfer(self.db, pt.id, None, pt.status, None, amount=net_amount)
            pt = update_payin_transfer(self.db, pt.id, None, pt.status, None)
            assert pt.amount == net_amount
        payin_transfers = self.db.all("""
            SELECT *
              FROM payin_transfers
             WHERE payin = %s
          ORDER BY ctime
        """, (payin.id,))
        fallback_remote_id = 'fake' if payin.status == 'succeeded' else None
        options_by_tippee = {tippee.id: opt for tippee, pt_amount, opt in transfers}
        for i, pt in enumerate(payin_transfers):
            opt = options_by_tippee[pt.team or pt.recipient]
            payin_transfers[i] = update_payin_transfer(
                self.db, pt.id, opt.get('remote_id', fallback_remote_id),
                opt.get('status', status), opt.get('error', error)
            )
            if pt.team:
                Participant.from_id(pt.recipient).update_receiving()
        for tippee, pt_amount, opt in transfers:
            tippee.update_receiving()
        payer.update_giving()
        # Call `update_payin` again to uncover bugs
        payin = update_payin(self.db, payin.id, remote_id, status, error)
        return payin, payin_transfers

    def add_payment_account(self, participant, provider, country='FR', **data):
        if provider == 'paypal':
            data.setdefault('id', participant.email or participant.username)
        else:
            data.setdefault('id', 'acct_1ChyayFk4eGpfLOC')
        data.setdefault('default_currency', None)
        data.setdefault('charges_enabled', True)
        data.setdefault('verified', True)
        data.setdefault('display_name', None)
        data.setdefault('token', None)
        data.update(p_id=participant.id, provider=provider, country=country)
        r = self.db.one("""
            INSERT INTO payment_accounts
                        (participant, provider, country, id,
                         default_currency, charges_enabled, verified,
                         display_name, token)
                 VALUES (%(p_id)s, %(provider)s, %(country)s, %(id)s,
                         %(default_currency)s, %(charges_enabled)s, %(verified)s,
                         %(display_name)s, %(token)s)
              RETURNING *
        """, data)
        participant.set_attributes(payment_providers=self.db.one("""
            SELECT payment_providers
              FROM participants
             WHERE id = %s
        """, (participant.id,)))
        return r

    def insert_email(self, address, participant_id, verified=True):
        verified_time = utcnow() if verified else None
        return self.db.one("""
            INSERT INTO emails
                        (address, verified, verified_time, participant)
                 VALUES (%(address)s, %(verified)s, %(verified_time)s, %(participant_id)s)
              RETURNING *
        """, locals())

    def upsert_route(self, participant, network,
                     status='chargeable', one_off=False, address='x', remote_user_id='x'):
        r = self.db.one("""
            INSERT INTO exchange_routes AS r
                        (participant, network, address, status, one_off, remote_user_id)
                 VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (participant, network, address) DO UPDATE
                    SET status = excluded.status
                      , one_off = excluded.one_off
                      , remote_user_id = excluded.remote_user_id
              RETURNING r
        """, (participant.id, network, address, status, one_off, remote_user_id))
        r.__dict__['participant'] = participant
        return r

    def attach_stripe_payment_method(self, participant, stripe_pm_id, one_off=False):
        pm = stripe.PaymentMethod.retrieve(stripe_pm_id)
        return ExchangeRoute.attach_stripe_payment_method(participant, pm, one_off)

    def make_invoice(self, sender, addressee, amount, status):
        invoice_data = {
            'nature': 'expense',
            'amount': str(amount.amount),
            'currency': amount.currency,
            'description': 'lorem ipsum',
            'details': '',
        }
        r = self.client.PxST(
            '/~%s/invoices/new' % addressee.id, auth_as=sender,
            data=invoice_data, xhr=True,
        )
        assert r.code == 200, r.text
        invoice_id = json.loads(r.text)['invoice_id']
        if status == 'pre':
            return invoice_id
        r = self.client.PxST(
            '/~%s/invoices/%s' % (addressee.id, invoice_id), auth_as=sender,
            data={'action': 'send'},
        )
        assert r.code == 302, r.text
        if status == 'new':
            return invoice_id
        r = self.client.PxST(
            '/~%s/invoices/%s' % (addressee.id, invoice_id), auth_as=addressee,
            data={'action': status[:-2], 'message': 'a message'},
        )
        assert r.code == 302, r.text
        return invoice_id


class Foobar(Exception): pass


@contextmanager
def postgres_readonly(db):
    db.readonly = True
    try:
        yield
    finally:
        db.readonly = False
