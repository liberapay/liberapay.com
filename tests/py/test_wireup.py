from datetime import timedelta
from importlib import reload
import sys
from time import sleep
import unittest
from unittest.mock import patch


class Test(unittest.TestCase):

    def setUp(self):
        for name in list(sys.modules):
            if name.split('.', 1)[0] in {'aspen', 'babel', 'liberapay', 'pando'}:
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

    @patch.dict('os.environ', {'RUN_CRON_JOBS': 'yes'})
    def test_98_main_starts_cron_jobs(self):
        import liberapay.cron
        now = liberapay.cron.utcnow()
        utcnow_patch = patch.object(liberapay.cron, 'utcnow', autospec=True)
        sleep_patch = patch.object(liberapay.cron, 'sleep')
        test_hook_patch = patch.object(liberapay.cron, 'break_before_call')
        with utcnow_patch as utcnow, sleep_patch as _sleep, test_hook_patch as test_hook:
            utcnow.return_value = now
            def forward_time(seconds):
                utcnow.return_value += timedelta(seconds=seconds)
            _sleep.side_effect = forward_time
            test_hook.return_value = True
            from liberapay.main import website
            assert website.cron
            assert website.cron.jobs
            for job in website.cron.jobs:
                print(job)
                if job.period:
                    for _ in range(10):
                        try:
                            if job.thread:
                                job.thread.join(10)
                        except RuntimeError:
                            pass
                        else:
                            break
                        sleep(0.1)

    @patch.dict('os.environ', {'RUN_CRON_JOBS': 'no'})
    def test_99_main_can_be_reloaded(self):
        import liberapay.main
        reload(liberapay.main)
