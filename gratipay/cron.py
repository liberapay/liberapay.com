import threading
import time
import traceback

from aspen import log_dammit


class Cron(object):

    def __init__(self, website):
        self.website = website
        self.conn = website.db.get_connection().__enter__()

    def __call__(self, period, func, exclusive=False):
        def f():
            if period <= 0:
                return
            sleep = time.sleep
            if exclusive:
                cursor = self.conn.cursor()
                try_lock = lambda: cursor.one("SELECT pg_try_advisory_lock(0)")
            has_lock = False
            while 1:
                try:
                    if exclusive and not has_lock:
                        has_lock = try_lock()
                    if not exclusive or has_lock:
                        func()
                except Exception, e:
                    self.website.tell_sentry(e)
                    log_dammit(traceback.format_exc().strip())
                sleep(period)
        t = threading.Thread(target=f)
        t.daemon = True
        t.start()
