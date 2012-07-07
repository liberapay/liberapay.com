from __future__ import unicode_literals
import unittest

import gittip
from gittip import wireup, testing


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
        self.db = gittip.db = wireup.db()
        testing.populate_db_with_dummy_data(self.db)
        self.conn = self.db.get_connection()

    def tearDown(self):
        # TODO: rollback transaction here so we don't fill up test db.
        pass
