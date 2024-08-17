from collections import namedtuple
from contextvars import copy_context
from datetime import timedelta
import logging
import threading
from time import sleep
import traceback

from pando.utils import utcnow
import psycopg2

from .constants import EPOCH


logger = logging.getLogger('liberapay.cron')


Daily = namedtuple('Daily', 'hour')
Weekly = namedtuple('Weekly', 'weekday hour')


class Cron:

    def __init__(self, website):
        self.website = website
        self.conn = None
        self._lock_thread = None
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
            while True:
                try:
                    g()
                except psycopg2.errors.IdleInTransactionSessionTimeout:
                    if self.has_lock:
                        self.has_lock = False
                    sleep(10)
                    self.conn = self.website.db.get_connection().__enter__()

        def g():
            cursor = self.conn.cursor()
            while True:
                if cursor.one("SELECT pg_try_advisory_lock(0)"):
                    if not self.has_lock:
                        self.has_lock = True
                        for job in self.jobs:
                            if job.exclusive:
                                job.start()
                else:
                    if self.has_lock:
                        self.has_lock = False
                sleep(55)
        t = self._lock_thread = threading.Thread(target=f, name="cron_waiter")
        t.daemon = True
        t.start()


class Job:

    __slots__ = (
        'cron', 'period', 'func', 'exclusive', 'running', 'thread',
        '_last_start_time',
    )

    def __init__(self, cron, period, func, exclusive=False):
        self.cron = cron
        self.period = period
        self.func = func
        self.exclusive = exclusive
        self.running = False
        self.thread = None
        self._last_start_time = None

    def __repr__(self):
        return f"Job(func={self.func!r}, period={self.period!r}, exclusive={self.exclusive!r}, thread={self.thread!r})"

    @property
    def last_start_time(self):
        if self.exclusive:
            return self.cron.website.db.one("""
                SELECT last_start_time
                  FROM cron_jobs
                 WHERE name = %s
            """, (self.func.__name__,))
        else:
            return self._last_start_time

    @last_start_time.setter
    def last_start_time(self, time):
        if self.exclusive:
            self.cron.website.db.run("""
                INSERT INTO cron_jobs
                            (name, last_start_time)
                     VALUES (%s, %s)
                ON CONFLICT (name) DO UPDATE
                        SET last_start_time = excluded.last_start_time
            """, (self.func.__name__, time))
        else:
            self._last_start_time = time

    def seconds_before_next_run(self):
        """Returns the time to wait before running this job.

        The returned value can be negative, indicating that the run should have
        already been started. If a run is very late, the returned negative value
        may not accurately represent how long ago the run should have started.
        """
        period, last_start_time = self.period, self.last_start_time
        now = utcnow()
        if isinstance(period, Weekly):
            then = now.replace(hour=period.hour, minute=10, second=0, microsecond=0)
            days = (period.weekday - now.isoweekday()) % 7
            if days:
                then += timedelta(days=days)
            if (last_start_time or EPOCH) >= then:
                then += timedelta(days=7)
        elif isinstance(period, Daily):
            then = now.replace(hour=period.hour, minute=5, second=0, microsecond=0)
            if (last_start_time or EPOCH) >= then:
                then += timedelta(days=1)
        elif period == 'irregular':
            return 0 if self.thread and self.thread.is_alive() else None
        elif last_start_time:
            then = last_start_time + timedelta(seconds=period)
        else:
            then = now
        return (then - now).total_seconds()

    def start(self):
        if self.thread and self.thread.is_alive() or not self.period:
            return

        func_name = self.func.__name__
        assert func_name != '<lambda>'

        def f():
            while True:
                try:
                    period = self.period
                    if period != 'irregular':
                        seconds = self.seconds_before_next_run()
                        if seconds > 0:
                            sleep(seconds)
                    if self.exclusive and not self.cron.has_lock:
                        return
                    if isinstance(period, (float, int)) and period < 300:
                        logger.debug(f"Running {self!r}")
                    else:
                        logger.info(f"Running {self!r}")
                    self.last_start_time = utcnow()
                    if break_before_call():
                        break
                    self.running = True
                    r = copy_context().run(self.func)
                    if break_after_call():
                        break
                except Exception as e:
                    self.running = False
                    self.cron.website.tell_sentry(e)
                    if self.exclusive:
                        while True:
                            try:
                                self.cron.website.db.run("""
                                    INSERT INTO cron_jobs
                                                (name, last_error_time, last_error)
                                         VALUES (%s, current_timestamp, %s)
                                    ON CONFLICT (name) DO UPDATE
                                            SET last_error_time = excluded.last_error_time
                                              , last_error = excluded.last_error
                                """, (func_name, traceback.format_exc()))
                            except psycopg2.OperationalError as e:
                                self.cron.website.tell_sentry(e)
                                # retry in a minute
                                sleep(60)
                            else:
                                break
                    # retry in a minute
                    sleep(60)
                    continue
                else:
                    self.running = False
                    if self.exclusive:
                        while True:
                            try:
                                self.cron.website.db.run("""
                                    INSERT INTO cron_jobs
                                                (name, last_success_time)
                                         VALUES (%s, current_timestamp)
                                    ON CONFLICT (name) DO UPDATE
                                            SET last_success_time = excluded.last_success_time
                                """, (func_name,))
                            except psycopg2.OperationalError as e:
                                self.cron.website.tell_sentry(e)
                                # retry in a minute
                                sleep(60)
                            else:
                                break
                    if period == 'irregular':
                        if r is None:
                            return
                        else:
                            sleep(r)

        t = self.thread = threading.Thread(target=f, name=func_name)
        t.daemon = True
        t.start()
        return t


def break_before_call():
    return False


def break_after_call():
    return False
