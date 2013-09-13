"""Helpers for testing Gittip.
"""
from __future__ import print_function, unicode_literals

import datetime
import random
import unittest
from decimal import Decimal
from os.path import join, dirname, realpath

import gittip
import pytz
from aspen import resources
from aspen.testing import Website, StubRequest
from aspen.utils import utcnow
from gittip.billing.payday import Payday
from gittip.models.participant import Participant
from gittip.security.user import User
from psycopg2 import IntegrityError


TOP = join(realpath(dirname(dirname(__file__))), '..')
SCHEMA = open(join(TOP, "schema.sql")).read()

DUMMY_GITHUB_JSON = u'{"html_url":"https://github.com/whit537","type":"User",'\
'"public_repos":25,"blog":"http://whit537.org/","gravatar_id":"fb054b407a6461'\
'e417ee6b6ae084da37","public_gists":29,"following":15,"updated_at":"2013-01-1'\
'4T13:43:23Z","company":"Gittip","events_url":"https://api.github.com/users/w'\
'hit537/events{/privacy}","repos_url":"https://api.github.com/users/whit537/r'\
'epos","gists_url":"https://api.github.com/users/whit537/gists{/gist_id}","em'\
'ail":"chad@zetaweb.com","organizations_url":"https://api.github.com/users/wh'\
'it537/orgs","hireable":false,"received_events_url":"https://api.github.com/u'\
'sers/whit537/received_events","starred_url":"https://api.github.com/users/wh'\
'it537/starred{/owner}{/repo}","login":"whit537","created_at":"2009-10-03T02:'\
'47:57Z","bio":"","url":"https://api.github.com/users/whit537","avatar_url":"'\
'https://secure.gravatar.com/avatar/fb054b407a6461e417ee6b6ae084da37?d=https:'\
'//a248.e.akamai.net/assets.github.com%2Fimages%2Fgravatars%2Fgravatar-user-4'\
'20.png","followers":90,"name":"Chad Whitacre","followers_url":"https://api.g'\
'ithub.com/users/whit537/followers","following_url":"https://api.github.com/u'\
'sers/whit537/following","id":134455,"location":"Pittsburgh, PA","subscriptio'\
'ns_url":"https://api.github.com/users/whit537/subscriptions"}'
# JSON data as returned from github for whit537 ;)

GITHUB_USER_UNREGISTERED_LGTEST = u'{"public_repos":0,"html_url":"https://git'\
'hub.com/lgtest","type":"User","repos_url":"https://api.github.com/users/lgte'\
'st/repos","gravatar_id":"d41d8cd98f00b204e9800998ecf8427e","following":0,"pu'\
'blic_gists":0,"updated_at":"2013-01-04T17:24:57Z","received_events_url":"htt'\
'ps://api.github.com/users/lgtest/received_events","gists_url":"https://api.g'\
'ithub.com/users/lgtest/gists{/gist_id}","events_url":"https://api.github.com'\
'/users/lgtest/events{/privacy}","organizations_url":"https://api.github.com/'\
'users/lgtest/orgs","avatar_url":"https://secure.gravatar.com/avatar/d41d8cd9'\
'8f00b204e9800998ecf8427e?d=https://a248.e.akamai.net/assets.github.com%2Fima'\
'ges%2Fgravatars%2Fgravatar-user-420.png","login":"lgtest","created_at":"2012'\
'-05-24T20:09:07Z","starred_url":"https://api.github.com/users/lgtest/starred'\
'{/owner}{/repo}","url":"https://api.github.com/users/lgtest","followers":0,"'\
'followers_url":"https://api.github.com/users/lgtest/followers","following_ur'\
'l":"https://api.github.com/users/lgtest/following","id":1775515,"subscriptio'\
'ns_url":"https://api.github.com/users/lgtest/subscriptions"}'
# JSON data as returned from github for unregistered user ``lgtest``

DUMMY_BOUNTYSOURCE_JSON = u'{"slug": "6-corytheboyd","updated_at": "2013-05-2'\
'4T01:45:20Z","last_name": "Boyd","id": 6,"last_seen_at": "2013-05-24T01:45:2'\
'0Z","email": "corytheboyd@gmail.com","fundraisers": [],"frontend_path": "#us'\
'ers/6-corytheboyd","display_name": "corytheboyd","frontend_url": "https://ww'\
'w.bountysource.com/#users/6-corytheboyd","created_at": "2012-09-14T03:28:07Z'\
'","first_name": "Cory","bounties": [],"image_url": "https://secure.gravatar.'\
'com/avatar/bdeaea505d059ccf23d8de5714ae7f73?d=https://a248.e.akamai.net/asse'\
'ts.github.com%2Fimages%2Fgravatars%2Fgravatar-user-420.png"}'
# JSON data as returned from bountysource for corytheboyd! hello, whit537 ;)


class Harness(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = gittip.db
        cls._tablenames = cls.db.all("SELECT tablename FROM pg_tables "
                                     "WHERE schemaname='public'")
        cls.clear_tables(cls.db, cls._tablenames[:])

    def tearDown(self):
        self.clear_tables(self.db, self._tablenames[:])

    @staticmethod
    def clear_tables(db, tablenames):
        while tablenames:
            tablename = tablenames.pop()
            try:
                # I tried TRUNCATE but that was way slower for me.
                db.run("DELETE FROM %s CASCADE" % tablename)
            except IntegrityError:
                tablenames.insert(0, tablename)

    def make_participant(self, username, **kw):
        participant = Participant.with_random_username()
        participant.change_username(username)

        # brute force update for use in testing
        for k,v in kw.items():
            if k == 'claimed_time':
                if v == 'now':
                    v = datetime.datetime.now(pytz.utc)
            self.db.run("UPDATE participants SET {}=%s WHERE username=%s" \
                        .format(k), (v, participant.username))
        participant.set_attributes(**kw)

        return participant


class GittipPaydayTest(Harness):

    def setUp(self):
        super(GittipPaydayTest, self).setUp()
        self.payday = Payday(self.db)


# Helpers for managing test data.
# ===============================

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
    for username, crap in _participants.items():
        (good_cc, is_suspicious, claimed, platform, user_id) = crap
        username_key = "login" if platform == 'github' else "screen_name"
        elsewhere.append({ "platform": platform
                         , "user_id": user_id
                         , "participant": username
                         , "user_info": { "id": user_id
                                        , username_key: username
                                         }
                          })
        rec = {"username": username}
        if good_cc is not None:
            rec["last_bill_result"] = "" if good_cc else "Failure!"
            rec["balanced_account_uri"] = "/v1/blah/blah/" + username
        rec["is_suspicious"] = is_suspicious
        if claimed:
            rec["claimed_time"] = then
        participants.append(rec)

    return ["participants"] + participants \
         + ["tips"] + tips \
         + ["elsewhere"] + elsewhere


def tip_graph(*a, **kw):
    context = load(*setup_tips(*a, **kw))

    def resolve_elsewhere(username):
        recs = context.db.all( "SELECT platform, user_id FROM elsewhere "
                               "WHERE participant=%s"
                             , (username,)
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
                       , '--show_tracebacks', str('yes')
                        ])

def serve_request(path, user=None):
    """Given an URL path, return response.
    """
    request = StubRequest(path)
    request.website = test_website
    if user is not None:
        user = User.from_username(user)
        # Note that Cookie needs a bytestring.
        request.headers.cookie[str('session')] = user.session_token
    response = test_website.handle_safely(request)
    return response

def load_request(path):
    """Given an URL path, return request.
    """
    request = StubRequest(path)
    request.website = test_website

    # XXX HACK - aspen.website should be refactored
    from aspen import dispatcher, sockets
    test_website.hooks.run('inbound_early', request)
    dispatcher.dispatch(request)  # sets request.fs
    request.socket = sockets.get(request)
    test_website.hooks.run('inbound_late', request)

    return request

def load_simplate(path):
    """Given an URL path, return resource.
    """
    request = load_request(path)
    return resources.get(request)
