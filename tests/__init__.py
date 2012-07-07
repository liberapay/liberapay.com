from __future__ import unicode_literals
import unittest

import gittip
from gittip import wireup, testing


class GittipBaseDBTest(unittest.TestCase):
    def setUp(self):
        self.db = gittip.db = wireup.db()
        testing.populate_db_with_dummy_data(self.db)
        self.conn = self.db.get_connection()

    def tearDown(self):
        # TODO: rollback transaction here so we don't fill up test db.
        pass
