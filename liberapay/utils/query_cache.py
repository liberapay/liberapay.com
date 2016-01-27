import sys
import threading
import time
import traceback


# Define a query cache.
# ==========================

class FormattingError(Exception):
    """Represent a problem with a format callable.
    """


class Entry(object):
    """An entry in a QueryCache.
    """

    timestamp = None    # The timestamp of the last query run [datetime.datetime]
    lock = None         # Access control for this record [threading.Lock]
    exc = None          # Any exception in query or formatting [Exception]

    def __init__(self, timestamp=0, lock=None, result=None):
        """Populate with dummy data or an actual db entry.
        """
        self.timestamp = timestamp
        self.lock = lock or threading.Lock()
        self.result = result


class QueryCache(object):
    """Implement a caching SQL post-processor.

    Instances of this object are callables that take two or more arguments. The
    first argument is a callback function; subsequent arguments are strings of
    SQL. The callback function will be given one result set per SQL query, and
    in the same order. These result sets are lists of dictionaries. The
    callback function may return any Python data type; this is the query
    result, post-processed for your application.

    The results of the callback are cached for <self.threshold> seconds
    (default: 5), keyed to the given SQL queries. NB: the cache is *not* keyed
    to the callback function, so cache entries with different callbacks will
    collide when operating on identical SQL queries. In this case cache entries
    can be differentiated by adding comments to the SQL statements.

    This so-called micro-caching helps greatly when under load, while keeping
    pages more or less fresh. For relatively static page elements like
    navigation, the time could certainly be extended. But even for page
    elements which are supposed to seem completely dynamic -- different for
    each page load -- you can profitably use this object with a low cache
    setting (1 or 2 seconds): the page will appear dynamic to any given user,
    but 100 requests in the same second will only result in one database call.

    This object also features a pruning thread, which removes stale cache
    entries on a more relaxed schedule (default: 60 seconds). It keeps the
    cache clean without interfering too much with actual usage.

    If the actual database call or the formatting callback raise an Exception,
    then that is cached as well, and will be raised on further calls until the
    cache expires as usual.

    And yes, Virginia, QueryCache is thread-safe (as long as you don't invoke
    the same instance again within your formatting callback).

    """

    db = None               # PostgresManager object
    cache = None            # the query cache [dictionary]
    locks = None            # access controls for self.cache [Locks]
    threshold = 5           # maximum life of a cache entry [seconds as int]
    threshold_prune = 60    # time between pruning runs [seconds as int]


    def __init__(self, db, threshold=5, threshold_prune=60):
        """
        """
        self.db = db
        self.threshold = threshold
        self.threshold_prune = threshold_prune
        self.cache = {}

        class Locks:
            checkin = threading.Lock()
            checkout = threading.Lock()
        self.locks = Locks()

        self.pruner = threading.Thread(target=self.prune)
        self.pruner.setDaemon(True)
        self.pruner.start()


    def one(self, query, params=None, process=None):
        return self._do_query(self.db.one, query, params, process)

    def all(self, query, params=None, process=None):
        if process is None:
            process = lambda g: list(g)
        return self._do_query(self.db.all, query, params, process)

    def _do_query(self, fetchfunc, query, params, process):
        """Given a function, a SQL string, a tuple, and a function, return ???.
        """

        # Compute a cache key.
        # ====================

        key = (query, params)


        # Check out an entry.
        # ===================
        # Each entry has its own lock, and "checking out" an entry means
        # acquiring that lock. If a queryset isn't yet in our cache, we first
        # "check in" a new dummy entry for it (and prevent other threads from
        # adding the same query), which will be populated presently.

        #thread_id = threading.currentThread().getName()[-1:] # for debugging
        #call_id = ''.join([random.choice(string.letters) for i in range(5)])

        self.locks.checkout.acquire()
        try:  # critical section
            if key in self.cache:

                # Retrieve an already cached query.
                # =================================
                # The cached entry may be a dummy. The best way to guarantee we
                # will catch this case is to simply refresh our entry after we
                # acquire its lock.

                entry = self.cache[key]
                entry.lock.acquire()
                entry = self.cache[key]

            else:

                # Add a new entry to our cache.
                # =============================

                dummy = Entry()
                dummy.lock.acquire()
                self.locks.checkin.acquire()
                try:  # critical section
                    if key in self.cache:
                        # Someone beat us to it. XXX: can this actually happen?
                        entry = self.cache[key]
                    else:
                        self.cache[key] = dummy
                        entry = dummy
                finally:
                    self.locks.checkin.release()

        finally:
            self.locks.checkout.release() # Now that we've checked out our
                                          # queryset, other threads are free to
                                          # check out other queries.


        # Process the query.
        # ==================

        try:  # critical section

            # Decide whether it's a hit or miss.
            # ==================================

            if time.time() - entry.timestamp < self.threshold:  # cache hit
                if entry.exc is not None:
                    raise entry.exc
                return entry.result

            else:                                               # cache miss
                try:                    # XXX uses postgres.py api, not dbapi2!
                    entry.result = fetchfunc(query, params)
                    if process is not None:
                        entry.result = process(entry.result)
                    entry.exc = None
                except:
                    entry.result = None
                    entry.exc = ( FormattingError(traceback.format_exc())
                                , sys.exc_info()[2]
                                 )


            # Check the queryset back in.
            # ===========================

            self.locks.checkin.acquire()
            try:  # critical section
                entry.timestamp = time.time()
                self.cache[key] = entry
                if entry.exc is not None:
                    raise entry.exc[0]
                else:
                    return entry.result
            finally:
                self.locks.checkin.release()

        finally:
            entry.lock.release()


    def prune(self):
        """Periodically remove any stale queries in our cache.
        """

        last = 0  # timestamp of last pruning run

        while 1:

            if time.time() < last + self.threshold_prune:
                # Not time to prune yet.
                time.sleep(0.2)
                continue

            self.locks.checkout.acquire()
            try:  # critical section

                for key, entry in tuple(self.cache.items()):

                    # Check out the entry.
                    # ====================
                    # If the entry is currently in use, skip it.

                    available = entry.lock.acquire(False)
                    if not available:
                        continue


                    # Remove the entry if it is too old.
                    # ==================================

                    try:  # critical section
                        if time.time() - entry.timestamp > self.threshold_prune:
                            del self.cache[key]
                    finally:
                        entry.lock.release()

            finally:
                self.locks.checkout.release()

            last = time.time()
