from collections import namedtuple
from datetime import datetime, timedelta
import logging
import threading
from time import sleep


CRON_ENCORE = 'CRON_ENCORE'
CRON_STOP = 'CRON_STOP'


logger = logging.getLogger('liberapay.cron')


Daily = namedtuple('Daily', 'hour')
Weekly = namedtuple('Weekly', 'weekday hour')


class Cron(object):

    def __init__(self, website):
        self.website = website
        self.conn = None
        self.has_lock = False
        self.jobs = []

    def __call__(self, period, func, exclusive=False):
        self.jobs.append((period, func, exclusive))
        if not self.website.env.run_cron_jobs or not period:
            return
        if exclusive and not self.has_lock:
            self._wait_for_lock()
            return
        def f():
            if isinstance(period, Weekly):
                while True:
                    now = datetime.utcnow()
                    then = now.replace(hour=period.hour, minute=10, second=0)
                    days = (period.weekday - now.isoweekday()) % 7
                    if days:
                        then += timedelta(days=days)
                    seconds = (then - now).total_seconds()
                    if seconds > 0:
                        sleep(seconds)
                    elif seconds < -60:
                        sleep(86400 * 6)
                        continue
                    try:
                        func()
                    except Exception as e:
                        self.website.tell_sentry(e, {})
                    sleep(86400 * 6)
            elif isinstance(period, Daily):
                while True:
                    now = datetime.utcnow()
                    then = now.replace(hour=period.hour, minute=5, second=0)
                    seconds = (then - now).total_seconds()
                    if seconds > 0:
                        # later today
                        sleep(seconds)
                    elif seconds < -60:
                        # tomorrow
                        sleep(3600 * 24 + seconds)
                    try:
                        func()
                    except Exception as e:
                        self.website.tell_sentry(e, {})
                        # retry in 5 minutes
                        sleep(300)
                    else:
                        # success, sleep until tomorrow
                        sleep(3600 * 23)
            elif period == 'once':
                while True:
                    try:
                        r = func()
                    except Exception as e:
                        self.website.tell_sentry(e, {})
                    else:
                        if r is CRON_ENCORE:
                            sleep(2)
                            continue
                    return
            else:
                while True:
                    try:
                        r = func()
                    except Exception as e:
                        self.website.tell_sentry(e, {})
                    else:
                        if r is CRON_ENCORE:
                            sleep(2)
                            continue
                        if r is CRON_STOP:
                            return
                    sleep(period)
        t = threading.Thread(target=f, name=func.__name__)
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
            for period, func, exclusive in self.jobs:
                if exclusive:
                    self(period, func, exclusive=True)
        t = threading.Thread(target=f)
        t.daemon = True
        t.start()
