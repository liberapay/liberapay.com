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


class Cron:

    def __init__(self, website):
        self.website = website
        self.conn = None
        self._wait_for_lock_thread = None
        self.has_lock = False
        self.jobs = []

    def __call__(self, period, func, exclusive=False):
        job = Job(self, period, func, exclusive)
        self.jobs.append(job)
        if not self.website.env.run_cron_jobs or not period:
            return
        if exclusive and not self.has_lock:
            self._wait_for_lock()
            return
        job.start()

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
            for job in self.jobs:
                if job.exclusive:
                    job.start()
        t = self._wait_for_lock_thread = threading.Thread(target=f)
        t.daemon = True
        t.start()


class Job:

    __slots__ = ('cron', 'period', 'func', 'exclusive', 'thread')

    def __init__(self, cron, period, func, exclusive=False):
        self.cron = cron
        self.period = period
        self.func = func
        self.exclusive = exclusive
        self.thread = None

    def __repr__(self):
        return f"Job(func={self.func!r}, period={self.period!r}, exclusive={self.exclusive!r}, thread={self.thread!r})"

    def start(self):
        if self.thread and self.thread.is_alive() or not self.period:
            return

        def f():
            while True:
                period = self.period
                if isinstance(period, Weekly):
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
                elif isinstance(period, Daily):
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
                    if isinstance(period, (float, int)) and period < 300:
                        logger.debug(f"Running {self!r}")
                    else:
                        logger.info(f"Running {self!r}")
                    if break_before_call():
                        break
                    r = self.func()
                    if break_after_call():
                        break
                except Exception as e:
                    self.cron.website.tell_sentry(e)
                    # retry in 5 minutes
                    sleep(300)
                    continue
                else:
                    if r is CRON_ENCORE:
                        sleep(2)
                        continue
                    if r is CRON_STOP:
                        return
                if period == 'once':
                    return
                elif isinstance(period, (float, int)):
                    sleep(period)
                else:
                    sleep(3600 * 23)

        t = self.thread = threading.Thread(target=f, name=self.func.__name__)
        t.daemon = True
        t.start()
        return t


def break_before_call():
    return False


def break_after_call():
    return False
