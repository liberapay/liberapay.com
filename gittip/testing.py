"""Helpers for testing Gittip.
"""
from __future__ import unicode_literals

import os
import re
import unittest
from decimal import Decimal
from os.path import join, dirname, realpath

import gittip
from aspen import resources
from aspen.testing import Website, StubRequest
from aspen.utils import utcnow
from gittip import wireup
from gittip.billing.payday import Payday


TOP = join(realpath(dirname(__file__)), '..')
SCHEMA = open(join(TOP, "schema.sql")).read()


def create_schema(db):
    db.execute(SCHEMA)

GITHUB_USERS = [ ("1775515", "lgtest")
               , ("1903357", "lglocktest")
               , ("1933953", "gittip-test-0")
               , ("1933959", "gittip-test-1")
               , ("1933965", "gittip-test-2")
               , ("1933967", "gittip-test-3")
                ]

def populate_db_with_dummy_data(db):
    from gittip.networks import github, change_participant_id
    for user_id, login in  GITHUB_USERS:
        participant_id, a,b,c = github.upsert({"id": user_id, "login": login})
        change_participant_id(None, participant_id, login)


class GittipBaseDBTest(unittest.TestCase):
    """

    Will setup a db connection so we can perform db operations. Everything is
    performed in a transaction and will be rolled back at the end of the test
    so we don't clutter up the db.

    """
    def setUp(self):
        populate_db_with_dummy_data(self.db)
        self.conn = self.db.get_connection()

    @classmethod
    def setUpClass(cls):
        cls.db = gittip.db = wireup.db()

    def tearDown(self):
        # TODO: rollback transaction here so we don't fill up test db.
        # TODO: hack for now, truncate all tables.
        tables = [
            'participants',
            'social_network_users',
            'tips',
            'transfers',
            'paydays',
            'exchanges',
        ]
        for t in tables:
            self.db.execute('truncate table %s cascade' % t)


class GittipPaydayTest(GittipBaseDBTest):

    def setUp(self):
        super(GittipPaydayTest, self).setUp()
        self.payday = Payday(self.db)


# Helpers for managing test data.
# ===============================

colname_re = re.compile("^[A-Za-z0-9_]+$")

class Context(object):
    """This is a context manager for testing.

    load = testing.Context()

    def test():
        with load(*data):
            actual = my_func()
            expected = "Cheese whiz!"
            assert actual == expected, actual

    """

    def __init__(self):
        self.db = wireup.db()
        self.billing = wireup.billing()
        self._delete_data()

    def __call__(self, *data):
        """Load up the database with data.

        Here's the format for data:

            ( "table1", (), {}
            , "table2", {}, [], {}
             )

        If it's a basestring it's a table name, if it's a dict it's a mapping
        of colname to value, if it's a tuple or list it's a sequence of values.

        """
        known_tables = self._get_table_names()
        table_name = ""

        for thing in data:

            typ = type(thing)

            if typ in (str, unicode):
                table_name = thing
                if table_name not in known_tables:  # SQLi pro
                    raise ValueError("Unknown table: %s" % table_name)
                continue

            if not table_name:
                raise ValueError("What table am I INSERTing into?")

            row = thing
            n = len(row)

            if typ is dict:
                colnames = []
                values = []
                for colname, value in sorted(row.iteritems()):
                    if colname_re.match(colname) is None:  # SQLi pro
                        raise ValueError( "colname must match %s"
                                        % colname_re.pattern)
                    colnames.append(colname)
                    values.append(value)
                colnames = ' (%s) ' % ', '.join(colnames)
            elif typ in (list, tuple):
                colnames = ' '
                values = thing

            values = tuple(values)
            value_placeholders = ', '.join(['%s'] * n)

            SQL = "INSERT INTO %s%sVALUES (%s)"
            SQL %= (table_name, colnames, value_placeholders)

            self.db.execute(SQL, values)

        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._delete_data()

    def diff(self):
        pass

    def dump(self):
        pass

    def _get_table_names(self):
        """Return a sorted list of tables in the public schema.
        """
        tables = self.db.fetchall("SELECT tablename FROM pg_tables "
                                  "WHERE schemaname='public'")
        if tables is None:
            tables = []
        else:
            tables = [rec['tablename'] for rec in tables]
        tables.sort()
        return tables

    def _delete_data(self):
        """Delete all data from all tables in the public schema (eep!).
        """
        safety_belt = os.environ["YES_PLEASE_DELETE_ALL_MY_DATA_VERY_OFTEN"]
        if safety_belt != "Pretty please, with sugar on top.":
            raise Exception("Heck.")

        for table_name in self._get_table_names():
            self.db.execute("TRUNCATE TABLE %s CASCADE" % table_name)

load = Context()

def start_payday():
    context = load()
    context.payday = Payday(gittip.db)
    return context


def setup_tips(*recs):
    """Setup some participants and tips. recs is a list of:

        ("tipper", "tippee", '2.00', False)
                                       ^
                                       |-- good cc?

    good_cc can be True, False, or None

    """
    data = []
    tips = []

    _participants = {}

    for tipper, tippee, amount, good_cc in recs:
        assert good_cc in (True, False, None), good_cc
        _participants[tipper] = good_cc
        if tippee not in _participants:
            _participants[tippee] = None
        now = utcnow()
        tips.append({ "ctime": now
                    , "mtime": now
                    , "tipper": tipper
                    , "tippee": tippee
                    , "amount": Decimal(amount)
                     })

    participants = []
    for participant_id, good_cc in _participants.items():
        rec = {"id": participant_id}
        if good_cc is not None:
            rec["last_bill_result"] = "" if good_cc else "Failure!"
        participants.append(rec)

    data = ["participants"] + participants + ["tips"] + tips
    return load(*data)


# Helpers for testing simplates.
# ==============================

test_website = Website([ '--www_root', str(join(TOP, 'www'))
                       , '--project_root', str('..')
                        ])

def serve_request(path):
    """Given an URL path, return response.
    """
    request = StubRequest(path)
    request.website = test_website
    response = test_website.handle_safely(request)
    return response

def load_simplate(path):
    """Given an URL path, return resource.
    """
    request = StubRequest(path)
    request.website = test_website

    # XXX HACK - aspen.website should be refactored
    from aspen import gauntlet, sockets
    test_website.hooks.inbound_early.run(request)
    gauntlet.run(request)  # sets request.fs
    request.socket = sockets.get(request)
    test_website.hooks.inbound_late.run(request)

    return resources.get(request)


if __name__ == "__main__":
    db = wireup.db()
    populate_db_with_dummy_data(db)
