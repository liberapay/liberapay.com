"""Helpers for testing.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

from contextlib import contextmanager
import itertools
import unittest
from os.path import dirname, join, realpath

from aspen import resources
from mangopay.utils import Money
from pando.utils import utcnow
from pando.testing.client import Client
from psycopg2 import IntegrityError, InternalError

from liberapay.billing import transactions
from liberapay.billing.transactions import (
    record_exchange, record_exchange_result, prepare_transfer, _record_transfer_result
)
from liberapay.constants import SESSION, ZERO
from liberapay.elsewhere._base import UserInfo
from liberapay.main import website
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.security.csrf import CSRF_TOKEN
from liberapay.testing.vcr import use_cassette


TOP = realpath(join(dirname(dirname(__file__)), '..'))
WWW_ROOT = str(realpath(join(TOP, 'www')))
PROJECT_ROOT = str(TOP)


def EUR(amount):
    return Money(amount, 'EUR')


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
            assert auth_as.session_token
            cookies = kw.setdefault('cookies', {})
            cookies[SESSION] = '%s:%s' % (auth_as.id, auth_as.session_token)

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
        resources.__cache__ = {}  # Clear the simplate cache.
        self.clear_tables()


    def clear_tables(self):
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
                self.tablenames.remove(tablename)
                self.tablenames.insert(0, tablename)
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
        for key in ('last_bill_result', 'balance', 'mangopay_wallet_id'):
            if key in kw:
                kw2[key] = kw.pop(key)

        kind = kw.setdefault('kind', 'individual')
        if kind not in ('group', 'community'):
            kw.setdefault('password', 'x')
            kw.setdefault('session_token', username)
            i = next(self.seq)
            kw.setdefault('mangopay_user_id', -i)
        kw.setdefault('status', 'active')
        if username:
            kw['username'] = username
        if 'join_time' not in kw:
            kw['join_time'] = utcnow()
        cols, vals = zip(*kw.items())
        cols = ', '.join(cols)
        placeholders = ', '.join(['%s']*len(vals))
        participant = self.db.one("""
            INSERT INTO participants
                        ({0})
                 VALUES ({1})
              RETURNING participants.*::participants
        """.format(cols, placeholders), vals)

        self.db.run("""
            INSERT INTO elsewhere
                        (platform, user_id, user_name, participant, domain)
                 VALUES (%s,%s,%s,%s,%s)
        """, (platform, participant.id, username, participant.id, domain))

        if kind not in ('group', 'community') and participant.mangopay_user_id:
            wallet_id = kw2.get('mangopay_wallet_id', -participant.id)
            zero = ZERO[participant.main_currency]
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
        if 'last_bill_result' in kw2:
            ExchangeRoute.insert(participant, 'mango-cc', '-1', kw2['last_bill_result'])
        if 'balance' in kw2 and kw2['balance'] != 0:
            self.make_exchange('mango-cc', kw2['balance'], 0, participant)

        return participant


    def make_stub(self, **kw):
        return Participant.make_stub(**kw)


    def fetch_payday(self):
        return self.db.one("SELECT * FROM paydays", back_as=dict)


    def make_exchange(self, route, amount, fee, participant, status='succeeded', error='', vat=0):
        if not isinstance(route, ExchangeRoute):
            network = route
            routes = ExchangeRoute.from_network(participant, network)
            if routes:
                route = routes[0]
            else:
                from .mangopay import MangopayHarness
                route = ExchangeRoute.insert(participant, network, MangopayHarness.card_id)
                assert route
        amount = amount if isinstance(amount, Money) else Money(amount, 'EUR')
        fee = fee if isinstance(fee, Money) else Money(fee, amount.currency)
        vat = vat if isinstance(vat, Money) else Money(vat, fee.currency)
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


class Foobar(Exception): pass


@contextmanager
def postgres_readonly(db):
    dbname = db.one("SELECT current_database()")
    db.run("ALTER DATABASE {0} SET default_transaction_read_only = true".format(dbname))
    try:
        yield
    finally:
        db.run("SET default_transaction_read_only = false")
        db.run("""
            BEGIN READ WRITE;
                ALTER DATABASE {0} SET default_transaction_read_only = false;
            END;
        """.format(dbname))
