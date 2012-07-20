"""Helpers for testing Gittip.
"""
from __future__ import unicode_literals

import unittest
from os.path import join, dirname, realpath

import gittip
from gittip import wireup
from gittip.billing.payday import Payday


SCHEMA = open(join(realpath(dirname(__file__)), "..", "schema.sql")).read()


def create_schema(db):
    db.execute(SCHEMA)


def populate_db_with_dummy_data(db):
    from gittip.networks import github
    github.upsert({"id": "1775515", "login": "lgtest"})
    github.upsert({"id": "1903357", "login": "lglocktest"})
    github.upsert({"id": "1933953", "login": "gittip-test-0"})
    github.upsert({"id": "1933959", "login": "gittip-test-1"})
    github.upsert({"id": "1933965", "login": "gittip-test-2"})
    github.upsert({"id": "1933967", "login": "gittip-test-3"})


class GittipBaseTest(unittest.TestCase):
    # TODO: rad common test methods here.
    pass


class GittipBaseDBTest(GittipBaseTest):
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
            'exchanges'
        ]
        for t in tables:
            self.db.execute('truncate table %s cascade' % t)

class GittipPaydayTest(GittipBaseDBTest):

    def setUp(self):
        super(GittipPaydayTest, self).setUp()
        self.payday = Payday(self.db)

if __name__ == "__main__":
    db = wireup.db() 
    populate_db_with_dummy_data(db)
