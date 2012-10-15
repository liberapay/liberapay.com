"""Helpers for testing Gittip.
"""
from __future__ import unicode_literals

import unittest
from os.path import join, dirname, realpath

import gittip
from aspen import resources
from aspen.testing import Website, StubRequest
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
    Similar to the above but will setup a db connection so we can perform db
    operations. Everything is performed in a transaction and will be rolled
    back at the end of the test so we don't clutter up the db.
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
