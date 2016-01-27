import threading
from time import sleep
import traceback

from aspen import log_dammit


class Cron(object):

    def __init__(self, website):
        self.website = website
        self.conn = None
        self.has_lock = False
        self.exclusive_jobs = []

    def __call__(self, period, func, exclusive=False):
        if period <= 0:
            return
        if exclusive and not self.has_lock:
            self.exclusive_jobs.append((period, func))
            self._wait_for_lock()
            return
        def f():
            while True:
                try:
                    func()
                except Exception as e:
                    self.website.tell_sentry(e, {})
                    log_dammit(traceback.format_exc().strip())
                sleep(period)
        t = threading.Thread(target=f)
        t.daemon = True
        t.start()

    def _wait_for_lock(self):
        if self.conn:
            return  # Already waiting
        self.conn = self.website.db.get_connection().__enter__()
        def f():
            cursor = self.conn.cursor()
            while True:
                if cursor.one("SELECT pg_try_advisory_lock(0)"):
                    self.has_lock = True
                    break
                sleep(300)
            for job in self.exclusive_jobs:
                self(*job, exclusive=True)
        t = threading.Thread(target=f)
        t.daemon = True
        t.start()
