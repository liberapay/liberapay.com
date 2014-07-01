"""Helpers for testing Gittip.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import itertools
import unittest
from decimal import Decimal
from os.path import join, dirname, realpath

from aspen import resources
from aspen.utils import utcnow
from aspen.testing.client import Client
from gittip.elsewhere import UserInfo
from gittip.models.account_elsewhere import AccountElsewhere
from gittip.models.participant import Participant
from gittip.security.user import User, SESSION
from gittip.testing.vcr import use_cassette
from gittip import wireup
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
        self.cookie[b'csrf_token'] = b'sotokeny'
        kw[b'HTTP_X-CSRF-TOKEN'] = b'sotokeny'

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
        cls.vcr_cassette = use_cassette(cls.__name__).__enter__()


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

        participant = Participant.with_random_username()
        participant.change_username(username)

        if 'elsewhere' in kw or 'claimed_time' in kw:
            username = participant.username
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
            cols, vals = zip(*kw.items())
            cols = ', '.join(cols)
            placeholders = ', '.join(['%s']*len(vals))
            participant = self.db.one("""
                UPDATE participants
                   SET ({0}) = ({1})
                 WHERE username=%s
             RETURNING participants.*::participants
            """.format(cols, placeholders), vals+(participant.username,))

        return participant


    def make_payday(self, *transfers):

        with self.db.get_cursor() as cursor:
            last_end = datetime.datetime(year=2012, month=1, day=1)
            last_end = cursor.one("SELECT ts_end FROM paydays ORDER BY ts_end DESC LIMIT 1", default=last_end)
            ts_end = last_end + datetime.timedelta(days=7)
            ts_start = ts_end - datetime.timedelta(hours=1)
            transfer_volume = Decimal(0)
            active = set()
            for i, (f, t, amount) in enumerate(transfers):
                cursor.run("INSERT INTO transfers (timestamp, tipper, tippee, amount, context)"
                              "VALUES (%s, %s, %s, %s, 'tip')",
                              (ts_start + datetime.timedelta(seconds=i), f, t, amount))
                transfer_volume += Decimal(amount)
                active.add(f)
                active.add(t)
            cursor.run("INSERT INTO paydays (ts_start, ts_end, nactive, transfer_volume) VALUES (%s, %s, %s, %s)",
                    (ts_start, ts_end, len(active), transfer_volume))
