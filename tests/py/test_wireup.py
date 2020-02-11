from importlib import reload
import unittest
from unittest.mock import patch
import sys


class Test(unittest.TestCase):

    def setUp(self):
        for name in list(sys.modules):
            if name.split('.', 1)[0] in {'aspen', 'liberapay', 'pando'}:
                sys.modules.pop(name, None)

    def test_01_main_doesnt_fail_when_db_is_down(self):
        with patch.dict('os.environ', {'DATABASE_URL': 'dbname=nonexistent'}):
            from liberapay.main import website, timers
            assert website
            # Check that a restart is scheduled
            assert timers
            # We don't actually want the timers to run during tests, so cancel them.
            for timer in timers:
                timer.cancel()
            # Check that the DB is attached to the website and models
            assert website.db.Participant.db is website.db
            # Check that `db.__bool__()` returns `False`
            assert bool(website.db) is False
            # Check that the website.platforms attribute exists
            assert website.platforms is website.db

    def test_99_main_can_be_reloaded(self):
        import liberapay.main
        reload(liberapay.main)
