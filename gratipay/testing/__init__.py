"""Helpers for testing Gratipay.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import atexit
import itertools
import unittest
from os.path import dirname, join, realpath

from aspen import resources
from aspen.utils import utcnow
from aspen.testing.client import Client
from gratipay.billing.exchanges import record_exchange, record_exchange_result
from gratipay.elsewhere import UserInfo
from gratipay.models.account_elsewhere import AccountElsewhere
from gratipay.security.user import User, SESSION
from gratipay.testing.vcr import use_cassette
from gratipay import wireup
from psycopg2 import IntegrityError, InternalError


TOP = realpath(join(dirname(dirname(__file__)), '..'))
SCHEMA = open(join(TOP, "schema.sql")).read()
WWW_ROOT = str(realpath(join(TOP, 'www')))
PROJECT_ROOT = str(TOP)


class ClientWithAuth(Client):

    def __init__(self, *a, **kw):
        Client.__init__(self, *a, **kw)
        Client.website = Client.hydrate_website(self)

    def build_wsgi_environ(self, *a, **kw):
        """Extend base class to support authenticating as a certain user.
        """

        # csrf - for both anon and authenticated
        csrf_token = kw.get('csrf_token', b'sotokeny')
        if csrf_token:
            self.cookie[b'csrf_token'] = csrf_token
            kw[b'HTTP_X-CSRF-TOKEN'] = csrf_token

        # user authentication
        auth_as = kw.pop('auth_as', None)
        if auth_as is None:
            if SESSION in self.cookie:
                del self.cookie[SESSION]
        else:
            user = User.from_username(auth_as)
            user.sign_in(self.cookie)

        return Client.build_wsgi_environ(self, *a, **kw)


class Harness(unittest.TestCase):

    client = ClientWithAuth(www_root=WWW_ROOT, project_root=PROJECT_ROOT)
    db = client.website.db
    platforms = client.website.platforms
    tablenames = db.all("SELECT tablename FROM pg_tables "
                        "WHERE schemaname='public'")
    seq = itertools.count(0)


    @classmethod
    def setUpClass(cls):
        cls.db.run("ALTER SEQUENCE exchanges_id_seq RESTART WITH 1")
        cls.setUpVCR()


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
                tablenames.insert(0, tablename)
        self.db.run("ALTER SEQUENCE participants_id_seq RESTART WITH 1")


    def make_elsewhere(self, platform, user_id, user_name, **kw):
        info = UserInfo( platform=platform
                       , user_id=unicode(user_id)
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
                widths[i] = max(widths[i], len(unicode(v)))
        for k, w in zip(data[0]._fields, widths):
            print("{0:{width}}".format(unicode(k), width=w), end=' | ')
        print()
        for row in data:
            for v, w in zip(row, widths):
                print("{0:{width}}".format(unicode(v), width=w), end=' | ')
            print()


    @classmethod
    def make_balanced_customer(cls):
        import balanced
        seq = next(cls.seq)
        return unicode(balanced.Customer(meta=dict(seq=seq)).save().href)


    def make_participant(self, username, **kw):
        # At this point wireup.db() has been called, but not ...
        wireup.username_restrictions(self.client.website)

        participant = self.db.one("""
            INSERT INTO participants
                        (username, username_lower)
                 VALUES (%s, %s)
              RETURNING participants.*::participants
        """, (username, username.lower()))

        if 'elsewhere' in kw or 'claimed_time' in kw:
            platform = kw.pop('elsewhere', 'github')
            self.db.run("""
                INSERT INTO elsewhere
                            (platform, user_id, user_name, participant)
                     VALUES (%s,%s,%s,%s)
            """, (platform, participant.id, username, username))

        # Update participant
        if kw:
            if kw.get('claimed_time') == 'now':
                kw['claimed_time'] = utcnow()
            if kw.get('balanced_customer_href') == 'new':
                kw['balanced_customer_href'] = self.make_balanced_customer()
            cols, vals = zip(*kw.items())
            cols = ', '.join(cols)
            placeholders = ', '.join(['%s']*len(vals))
            participant = self.db.one("""
                UPDATE participants
                   SET ({0}) = ({1})
                 WHERE username=%s
             RETURNING participants.*::participants
            """.format(cols, placeholders), vals+(username,))

        return participant


    def fetch_payday(self):
        return self.db.one("SELECT * FROM paydays", back_as=dict)


    def make_exchange(self, kind, amount, fee, participant, status='succeeded', error=''):
        e_id = record_exchange(self.db, kind, amount, fee, participant, 'pre')
        record_exchange_result(self.db, e_id, status, error, participant)
        return e_id


class Foobar(Exception): pass


atexit.register(lambda: wireup.clean_assets(WWW_ROOT))
