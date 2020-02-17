"""Helpers for testing.
"""

from contextlib import contextmanager
import itertools
import unittest
from os.path import dirname, join, realpath

from pando.utils import utcnow
from pando.testing.client import Client
from psycopg2 import IntegrityError, InternalError
import stripe

from liberapay.billing import transactions
from liberapay.billing.transactions import (
    record_exchange, record_exchange_result, prepare_transfer, _record_transfer_result
)
from liberapay.constants import SESSION
from liberapay.elsewhere._base import UserInfo
from liberapay.exceptions import MissingPaymentAccount
from liberapay.i18n.currencies import Money
from liberapay.main import website
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.payin.common import (
    adjust_payin_transfers, prepare_donation, prepare_payin,
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


class ClientWithAuth(Client):

    def __init__(self, *a, **kw):
        Client.__init__(self, *a, **kw)
        Client.website = website

    def build_wsgi_environ(self, *a, **kw):
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

        return Client.build_wsgi_environ(self, *a, **kw)

    def hit(self, *a, **kw):
        if kw.pop('xhr', False):
            kw['HTTP_X_REQUESTED_WITH'] = b'XMLHttpRequest'

        # prevent tell_sentry from reraising errors
        if not kw.pop('sentry_reraise', True):
            env = self.website.env
            old_reraise, env.sentry_reraise = env.sentry_reraise, False
            try:
                return super(ClientWithAuth, self).hit(*a, **kw)
            finally:
                env.sentry_reraise = old_reraise

        return super(ClientWithAuth, self).hit(*a, **kw)


class Harness(unittest.TestCase):

    QUARANTINE = transactions.QUARANTINE
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
    seq = itertools.count(0)


    @classmethod
    def setUpClass(cls):
        cls_name = cls.__name__
        if cls_name[4:5].isupper():
            cls_id = sum(ord(c) - 97 << (i*5) for i, c in enumerate(cls_name[4:10].lower()))
        else:
            cls_id = 1
        cls.db.run("ALTER SEQUENCE exchanges_id_seq RESTART WITH %s", (cls_id,))
        cls.db.run("ALTER SEQUENCE transfers_id_seq RESTART WITH %s", (cls_id,))
        cls.setUpVCR()
        transactions.QUARANTINE = '0 seconds'


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
        transactions.QUARANTINE = cls.QUARANTINE


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


    def make_elsewhere(self, platform, user_id, user_name, domain='', **kw):
        info = UserInfo(platform=platform, user_id=str(user_id),
                        user_name=user_name, domain=domain, **kw)
        return AccountElsewhere.upsert(info)


    def make_participant(self, username, **kw):
        platform = kw.pop('elsewhere', 'github')
        domain = kw.pop('domain', '')
        kw2 = {}
        for key in ('balance', 'mangopay_wallet_id'):
            if key in kw:
                kw2[key] = kw.pop(key)

        kind = kw.setdefault('kind', 'individual')
        is_person = kind not in ('group', 'community')
        if is_person:
            i = next(self.seq)
            kw.setdefault('mangopay_user_id', -i)
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

        if is_person and participant.mangopay_user_id:
            wallet_id = kw2.get('mangopay_wallet_id', -participant.id)
            zero = Money.ZEROS[participant.main_currency]
            self.db.run("""
                INSERT INTO wallets
                            (remote_id, balance, owner, remote_owner_id)
                     VALUES (%s, %s, %s, %s)
            """, (wallet_id, zero, participant.id, participant.mangopay_user_id))

        if 'email' in kw:
            self.db.run("""
                INSERT INTO emails
                            (participant, address, verified, verified_time)
                     VALUES (%s, %s, true, now())
            """, (participant.id, kw['email']))
        if 'balance' in kw2 and kw2['balance'] != 0:
            self.make_exchange('mango-cc', kw2['balance'], 0, participant)

        return participant


    def make_stub(self, **kw):
        return Participant.make_stub(**kw)


    def fetch_payday(self):
        return self.db.one("SELECT * FROM paydays", back_as=dict)


    def make_exchange(self, route, amount, fee, participant, status='succeeded', error='', vat=0):
        amount = amount if isinstance(amount, Money) else Money(amount, 'EUR')
        fee = fee if isinstance(fee, Money) else Money(fee, amount.currency)
        vat = vat if isinstance(vat, Money) else Money(vat, fee.currency)
        if not isinstance(route, ExchangeRoute):
            network = route
            currency = amount.currency if network == 'mango-cc' else None
            routes = ExchangeRoute.from_network(participant, network, currency=currency)
            if routes:
                route = routes[0]
            else:
                from .mangopay import MangopayHarness
                address = MangopayHarness.card_id if network == 'mango-cc' else -participant.id
                route = ExchangeRoute.insert(participant, network, address, 'chargeable', currency=currency)
                assert route
        e_id = record_exchange(self.db, route, amount, fee, vat, participant, 'pre').id
        record_exchange_result(self.db, e_id, -e_id, status, error, participant)
        return e_id


    def make_transfer(self, tipper, tippee, amount, context='tip', team=None, status='succeeded'):
        wallet_from, wallet_to = '-%i' % tipper, '-%i' % tippee
        t_id = prepare_transfer(
            self.db, tipper, tippee, amount, context, wallet_from, wallet_to, team=team
        )
        _record_transfer_result(self.db, t_id, status)
        return t_id


    def get_balances(self):
        return dict(self.db.all("""
            SELECT p.username, basket_sum(w.balance) AS balances
              FROM wallets w
              JOIN participants p ON p.id = w.owner
          GROUP BY p.username
        """))


    def make_payin_and_transfer(
        self, route, tippee, amount,
        status='succeeded', error=None, payer_country=None, fee=None,
        remote_id='fake', **opt
    ):
        payin, payin_transfers = self.make_payin_and_transfers(
            route, amount, [(tippee, amount, opt)],
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
        payin = prepare_payin(self.db, payer, amount, route)
        provider = route.network.split('-', 1)[0]
        for tippee, pt_amount, opt in transfers:
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
                    prepare_donation(
                        self.db, payin, tip, tippee, provider, payer, payer_country, pt_amount
                    )
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
        payin = update_payin(self.db, payin.id, remote_id, status, error, fee=fee)
        net_amount = payin.amount - (fee or 0)
        adjust_payin_transfers(self.db, payin, net_amount)
        payin_transfers = self.db.all("""
            SELECT *
              FROM payin_transfers
             WHERE payin = %s
          ORDER BY ctime
        """, (payin.id,))
        for tippee, pt_amount, opt in transfers:
            for i, pt in enumerate(payin_transfers):
                payin_transfers[i] = update_payin_transfer(
                    self.db, pt.id, opt.get('remote_id', 'fake'),
                    opt.get('status', status), opt.get('error', error)
                )
                if pt.team:
                    Participant.from_id(pt.recipient).update_receiving()
            tippee.update_receiving()
        payer.update_giving()
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
        return self.db.one("""
            INSERT INTO payment_accounts
                        (participant, provider, country, id,
                         default_currency, charges_enabled, verified,
                         display_name, token)
                 VALUES (%(p_id)s, %(provider)s, %(country)s, %(id)s,
                         %(default_currency)s, %(charges_enabled)s, %(verified)s,
                         %(display_name)s, %(token)s)
              RETURNING *
        """, data)

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


class Foobar(Exception): pass


@contextmanager
def postgres_readonly(db):
    db.readonly = True
    try:
        yield
    finally:
        db.readonly = False
