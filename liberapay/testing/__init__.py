"""Helpers for testing.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import itertools
import unittest
from os.path import dirname, join, realpath

from aspen import resources, Response
from aspen.utils import utcnow
from aspen.testing.client import Client
from liberapay.billing import exchanges
from liberapay.billing.exchanges import (
    record_exchange, record_exchange_result, _record_transfer_result
)
from liberapay.constants import SESSION
from liberapay.elsewhere import UserInfo
from liberapay.main import website
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.models.participant import Participant
from liberapay.testing.vcr import use_cassette
from psycopg2 import IntegrityError, InternalError


TOP = realpath(join(dirname(dirname(__file__)), '..'))
WWW_ROOT = str(realpath(join(TOP, 'www')))
PROJECT_ROOT = str(TOP)


class ClientWithAuth(Client):

    def __init__(self, *a, **kw):
        Client.__init__(self, *a, **kw)
        Client.website = website

    def build_wsgi_environ(self, *a, **kw):
        """Extend base class to support authenticating as a certain user.
        """

        self.cookie.clear()

        # csrf - for both anon and authenticated
        csrf_token = kw.get('csrf_token', b'ThisIsATokenThatIsThirtyTwoBytes')
        if csrf_token:
            self.cookie[b'csrf_token'] = csrf_token
            kw[b'HTTP_X-CSRF-TOKEN'] = csrf_token

        # user authentication
        auth_as = kw.pop('auth_as', None)
        if auth_as:
            assert auth_as.session_token
            self.cookie[SESSION] = '%s:%s' % (auth_as.id, auth_as.session_token)

        for k, v in kw.pop('cookies', {}).items():
            self.cookie[k] = v

        return Client.build_wsgi_environ(self, *a, **kw)

    def hit(self, *a, **kw):
        if kw.pop('xhr', False):
            kw[b'HTTP_X_REQUESTED_WITH'] = b'XMLHttpRequest'
        return super(ClientWithAuth, self).hit(*a, **kw)


def decode_body(self):
    body = self.body
    return body.decode(self.charset) if isinstance(body, bytes) else body

Response.text = property(decode_body)


class Harness(unittest.TestCase):

    QUARANTINE = exchanges.QUARANTINE
    client = ClientWithAuth(www_root=WWW_ROOT, project_root=PROJECT_ROOT)
    db = client.website.db
    platforms = client.website.platforms
    tablenames = db.all("SELECT tablename FROM pg_tables "
                        "WHERE schemaname='public'")
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
        exchanges.QUARANTINE = '0 seconds'


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
        exchanges.QUARANTINE = cls.QUARANTINE


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


    def make_elsewhere(self, platform, user_id, user_name, **kw):
        info = UserInfo( platform=platform
                       , user_id=str(user_id)
                       , user_name=user_name
                       , **kw
                       )
        return AccountElsewhere.upsert(info)


    def show_table(self, table):
        print('\n{:=^80}'.format(table))
        data = self.db.all('select * from '+table, back_as='namedtuple')
        if len(data) == 0:
            return
        widths = list(len(k) for k in data[0]._fields)
        for row in data:
            for i, v in enumerate(row):
                widths[i] = max(widths[i], len(str(v)))
        for k, w in zip(data[0]._fields, widths):
            print("{0:{width}}".format(str(k), width=w), end=' | ')
        print()
        for row in data:
            for v, w in zip(row, widths):
                print("{0:{width}}".format(str(v), width=w), end=' | ')
            print()


    def make_participant(self, username, **kw):
        platform = kw.pop('elsewhere', 'github')
        kw2 = {}
        for key in ('last_bill_result', 'balance'):
            if key in kw:
                kw2[key] = kw.pop(key)

        kind = kw.setdefault('kind', 'individual')
        if kind not in ('group', 'community'):
            kw.setdefault('password', 'x')
            kw.setdefault('session_token', username)
        kw.setdefault('status', 'active')
        if not 'join_time' in kw:
            kw['join_time'] = utcnow()
        i = next(self.seq)
        kw.setdefault('mangopay_user_id', -i)
        kw.setdefault('mangopay_wallet_id', -i)
        cols, vals = zip(*kw.items())
        cols = ', '.join(cols)
        placeholders = ', '.join(['%s']*len(vals))
        participant = self.db.one("""
            INSERT INTO participants
                        (username, {0})
                 VALUES (%s, {1})
              RETURNING participants.*::participants
        """.format(cols, placeholders), (username,)+vals)

        self.db.run("""
            INSERT INTO elsewhere
                        (platform, user_id, user_name, participant)
                 VALUES (%s,%s,%s,%s)
        """, (platform, participant.id, username, participant.id))

        if 'last_bill_result' in kw2:
            ExchangeRoute.insert(participant, 'mango-cc', '-1', kw2['last_bill_result'])
        if 'balance' in kw2:
            self.make_exchange('mango-cc', kw2['balance'], 0, participant)

        return participant


    def make_stub(self, **kw):
        return Participant.make_stub(**kw)


    def fetch_payday(self):
        return self.db.one("SELECT * FROM paydays", back_as=dict)


    def make_exchange(self, route, amount, fee, participant, status='succeeded', error=''):
        if not isinstance(route, ExchangeRoute):
            network = route
            route = ExchangeRoute.from_network(participant, network)
            if not route:
                from .mangopay import MangopayHarness
                route = ExchangeRoute.insert(participant, network, MangopayHarness.card_id)
                assert route
        e_id = record_exchange(self.db, route, amount, fee, participant, 'pre')
        record_exchange_result(self.db, e_id, status, error, participant)
        return e_id


    def make_transfer(self, tipper, tippee, amount, context='tip', team=None, status='succeeded'):
        t_id = self.db.one("""
            INSERT INTO transfers
                        (tipper, tippee, amount, context, team, status)
                 VALUES (%s, %s, %s, %s, %s, 'pre')
              RETURNING id
        """, (tipper, tippee, amount, context, team))
        _record_transfer_result(self.db, t_id, status)
        return t_id


class Foobar(Exception): pass
