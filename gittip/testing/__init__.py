"""Helpers for testing Gittip.
"""
from __future__ import unicode_literals

import datetime
import copy
import os
import random
import re
import unittest
from decimal import Decimal
from os.path import join, dirname, realpath

import gittip
from aspen import resources
from aspen.testing import Website, StubRequest
from aspen.utils import utcnow
from gittip import orm, wireup
from gittip.models.participant import Participant
from gittip.authentication import User
from gittip.billing.payday import Payday


TOP = join(realpath(dirname(dirname(__file__))), '..')
SCHEMA = open(join(TOP, "schema.sql")).read()

DUMMY_GITHUB_JSON = u'{"html_url":"https://github.com/whit537","type":"User","public_repos":25,"blog":"http://whit537.org/","gravatar_id":"fb054b407a6461e417ee6b6ae084da37","public_gists":29,"following":15,"updated_at":"2013-01-14T13:43:23Z","company":"Gittip","events_url":"https://api.github.com/users/whit537/events{/privacy}","repos_url":"https://api.github.com/users/whit537/repos","gists_url":"https://api.github.com/users/whit537/gists{/gist_id}","email":"chad@zetaweb.com","organizations_url":"https://api.github.com/users/whit537/orgs","hireable":false,"received_events_url":"https://api.github.com/users/whit537/received_events","starred_url":"https://api.github.com/users/whit537/starred{/owner}{/repo}","login":"whit537","created_at":"2009-10-03T02:47:57Z","bio":"","url":"https://api.github.com/users/whit537","avatar_url":"https://secure.gravatar.com/avatar/fb054b407a6461e417ee6b6ae084da37?d=https://a248.e.akamai.net/assets.github.com%2Fimages%2Fgravatars%2Fgravatar-user-420.png","followers":90,"name":"Chad Whitacre","followers_url":"https://api.github.com/users/whit537/followers","following_url":"https://api.github.com/users/whit537/following","id":134455,"location":"Pittsburgh, PA","subscriptions_url":"https://api.github.com/users/whit537/subscriptions"}'
"JSON data as returned from github for whit537 ;)"

GITHUB_USER_UNREGISTERED_LGTEST = u'{"public_repos":0,"html_url":"https://github.com/lgtest","type":"User","repos_url":"https://api.github.com/users/lgtest/repos","gravatar_id":"d41d8cd98f00b204e9800998ecf8427e","following":0,"public_gists":0,"updated_at":"2013-01-04T17:24:57Z","received_events_url":"https://api.github.com/users/lgtest/received_events","gists_url":"https://api.github.com/users/lgtest/gists{/gist_id}","events_url":"https://api.github.com/users/lgtest/events{/privacy}","organizations_url":"https://api.github.com/users/lgtest/orgs","avatar_url":"https://secure.gravatar.com/avatar/d41d8cd98f00b204e9800998ecf8427e?d=https://a248.e.akamai.net/assets.github.com%2Fimages%2Fgravatars%2Fgravatar-user-420.png","login":"lgtest","created_at":"2012-05-24T20:09:07Z","starred_url":"https://api.github.com/users/lgtest/starred{/owner}{/repo}","url":"https://api.github.com/users/lgtest","followers":0,"followers_url":"https://api.github.com/users/lgtest/followers","following_url":"https://api.github.com/users/lgtest/following","id":1775515,"subscriptions_url":"https://api.github.com/users/lgtest/subscriptions"}'
"JSON data as returned from github for unregistered user ``lgtest``"


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
    from gittip.elsewhere.github import GitHubAccount
    from gittip.participant import Participant
    for user_id, login in GITHUB_USERS:
        account = GitHubAccount(user_id, {"id": user_id, "login": login})
        Participant(account.participant_id).change_id(login)


class Harness(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = orm.db
        cls.session = orm.db.session

    def setUp(self):
        pass

    def tearDown(self):
        self.db.empty_tables()

    def make_participant(self, participant_id, **kw):
        participant = Participant(id=participant_id, **kw)
        self.session.add(participant)
        self.session.commit()
        return participant


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
        tables = [ 'participants'
                 , 'elsewhere'
                 , 'tips'
                 , 'transfers'
                 , 'paydays'
                 , 'exchanges'
                 , 'absorptions'
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

        self.a = self.dump()
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        orm.rollback()
        self._delete_data()

    def diff(self, compact=False):
        """Compare the data state now with when we started.
        """
        a = copy.deepcopy(self.a)  # avoid mutation
        b = self.dump()
        return self._diff(a, b, compact)

    def _diff(self, a, b, compact):
        """Compare two data dumps.
        """
        out = {}
        pkeys = self._get_primary_keys()
        assert sorted(a.keys()) == sorted(b.keys()), \
                                           "Sorry, diff isn't designed for DDL"
        for table_name, b_table in b.items():
            a_table = a[table_name]

            inserts = []
            updates = []
            deletes = []

            # Be sure to sort {a,b}_table.items() so we can depend on the sort
            # order of the inserts, updates, and deletes lists.
            # See https://github.com/zetaweb/www.gittip.com/issues/413.

            for key, row in sorted(b_table.items()):
                if key not in a_table:
                    inserts.append(row)
                else:
                    update = {}
                    for colname, value in row.items():
                        if a_table[key][colname] != value:
                            update[colname] = value
                    if update:
                        pkey = pkeys[table_name]
                        update[pkey] = row[pkey] # include primary key
                        updates.append(update)

            for key, row in sorted(a_table.items()):
                if key not in b_table:
                    deletes.append(row)

            if inserts or updates or deletes:
                out[table_name] = {}
                if compact:
                    out[table_name] = [ len(inserts)
                                      , len(updates)
                                      , len(deletes)
                                       ]
                else:
                    out[table_name] = { "inserts": inserts
                                      , "updates": updates
                                      , "deletes": deletes
                                       }

        return out

    def dump(self):
        """Return a dump of the database.

        Format:

            { "table1": {1: {}, 2: {}}
            , "table2": {1: {}}
             }

        That's table name to a mapping of primary key to the entire row as a
        dict.

        """
        out = {}
        pkeys = self._get_primary_keys()
        for table_name in self._get_table_names():
            pkey = pkeys[table_name]
            rows = self.db.fetchall("SELECT * FROM %s ORDER BY %s"
                                   % (table_name, pkey))
            if rows is None:
                rows = []
            mapped = {}
            for row in rows:
                key = row[pkey]
                mapped[key] = row
            out[table_name] = mapped
        return out

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

    def _get_primary_keys(self):
        """Return a mapping of table name in the public schema to primary key.
        """
        _pkeys = self.db.fetchall("""

            SELECT tablename, indexdef
              FROM pg_indexes
             WHERE schemaname='public'
               AND indexname LIKE '%_pkey'

        """)
        if _pkeys is None:
            _pkeys = []
        else:
            pkeys = {}
            for row in _pkeys:
                pkey = row['indexdef'].split('(')[1].split(')')[0]
                pkeys[row['tablename']] = pkey
        return pkeys

    def _delete_data(self):
        """Delete all data from all tables in the public schema (eep!).
        """
        safety_belt = os.environ["YES_PLEASE_DELETE_ALL_MY_DATA_VERY_OFTEN"]
        if safety_belt != "Pretty please, with sugar on top.":
            raise Exception("Heck.")

        for table_name in self._get_table_names():
            self.db.execute("TRUNCATE TABLE %s CASCADE" % table_name)

load = Context()

def start_payday(*data):
    context = load(*data)
    context.payday = Payday(gittip.db)
    ts_start = context.payday.start()
    context.payday.zero_out_pending(ts_start)
    context.ts_start = ts_start
    return context


def setup_tips(*recs):
    """Setup some participants and tips. recs is a list of:

        ("tipper", "tippee", '2.00', True, False, True, "github", "12345")
                                       ^     ^      ^
                                       |     |      |
                                       |     |      -- claimed?
                                       |     -- is_suspicious?
                                       |-- good cc?

    tipper must be a unicode
    tippee can be None or unicode
    amount can be None or unicode
    good_cc can be True, False, or None
    is_suspicious can be True, False, or None
    claimed can be True or False
    platform can be unicode
    user_id can be unicode

    """
    tips = []

    _participants = {}
    randid = lambda: unicode(random.randint(1, 1000000))

    for rec in recs:
        good_cc, is_suspicious, claimed, platform, user_id = \
                                        (True, False, True, "github", randid())

        if len(rec) == 3:
            tipper, tippee, amount = rec
        elif len(rec) == 4:
            tipper, tippee, amount, good_cc = rec
            is_suspicious, claimed = (False, True)
        elif len(rec) == 5:
            tipper, tippee, amount, good_cc, is_suspicious = rec
            claimed = True
        elif len(rec) == 6:
            tipper, tippee, amount, good_cc, is_suspicious, claimed = rec
        elif len(rec) == 7:
            tipper, tippee, amount, good_cc, is_suspicious, claimed, platform \
                                                                          = rec
        elif len(rec) == 8:
            tipper, tippee, amount, good_cc, is_suspicious, claimed, \
                                                        platform, user_id = rec
        else:
            raise Exception(rec)

        assert good_cc in (True, False, None), good_cc
        assert is_suspicious in (True, False, None), is_suspicious
        _participants[tipper] = \
                              (good_cc, is_suspicious, True, platform, user_id)

        if tippee is None:
            continue
        assert claimed in (True, False), claimed  # refers to tippee
        if tippee not in _participants:
            _participants[tippee] = (None, False, claimed, "github", randid())
        now = utcnow()
        tips.append({ "ctime": now
                    , "mtime": now
                    , "tipper": tipper
                    , "tippee": tippee
                    , "amount": Decimal(amount)
                     })

    then = utcnow() - datetime.timedelta(seconds=3600)

    participants = []
    elsewhere = []
    for participant_id, crap in _participants.items():
        (good_cc, is_suspicious, claimed, platform, user_id) = crap
        username_key = "login" if platform == 'github' else "screen_name"
        elsewhere.append({ "platform": platform
                         , "user_id": user_id
                         , "participant_id": participant_id
                         , "user_info": { "id": user_id
                                        , username_key: participant_id
                                         }
                          })
        rec = {"id": participant_id}
        if good_cc is not None:
            rec["last_bill_result"] = "" if good_cc else "Failure!"
            rec["balanced_account_uri"] = "/v1/blah/blah/" + participant_id
        rec["is_suspicious"] = is_suspicious
        if claimed:
            rec["claimed_time"] = then
        participants.append(rec)

    return ["participants"] + participants \
         + ["tips"] + tips \
         + ["elsewhere"] + elsewhere


def tip_graph(*a, **kw):
    context = load(*setup_tips(*a, **kw))

    def resolve_elsewhere(participant_id):
        recs = context.db.fetchall( "SELECT platform, user_id FROM elsewhere "
                                    "WHERE participant_id=%s"
                                  , (participant_id,)
                                   )
        if recs is not None:
            recs = [(rec['platform'], rec['user_id']) for rec in recs]
        return recs

    context.resolve_elsewhere = resolve_elsewhere  # Wheeee! :D

    return context


# Helpers for testing simplates.
# ==============================

test_website = Website([ '--www_root', str(join(TOP, 'www'))
                       , '--project_root', str(TOP)
                        ])

def serve_request(path, user=None):
    """Given an URL path, return response.
    """
    request = StubRequest(path)
    request.website = test_website
    if user is not None:
        user = User.from_id(user)
        # Note that Cookie needs a bytestring.
        request.headers.cookie[str('session')] = user.session_token
    response = test_website.handle_safely(request)
    return response

def load_simplate(path):
    """Given an URL path, return resource.
    """
    request = StubRequest(path)
    request.website = test_website

    # XXX HACK - aspen.website should be refactored
    from aspen import dispatcher, sockets
    test_website.hooks.run('inbound_early', request)
    dispatcher.dispatch(request)  # sets request.fs
    request.socket = sockets.get(request)
    test_website.hooks.run('inbound_late', request)

    return resources.get(request)

if __name__ == "__main__":
    db = wireup.db()
    populate_db_with_dummy_data(db)
