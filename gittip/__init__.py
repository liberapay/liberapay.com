import datetime
import locale
import os
from decimal import Decimal


try:  # XXX This can't be right.
    locale.setlocale(locale.LC_ALL, "en_US.utf8")
except locale.Error:
    locale.setlocale(locale.LC_ALL, "en_US.UTF-8")


BIRTHDAY = datetime.date(2012, 6, 1)
CARDINALS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']
MONTHS = [None, 'January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']

def age():
    today = datetime.date.today()
    nmonths = today.month - BIRTHDAY.month
    plural = 's' if nmonths != 1 else ''
    if nmonths < 10:
        nmonths = CARDINALS[nmonths]
    else:
        nmonths = str(nmonths)
    return "%s month%s" % (nmonths, plural)


db = None # This global is wired in wireup. It's an instance of
          # gittip.postgres.PostgresManager.

# Not sure we won't want this for something yet. Prune if you don't find it in
# the codebase in a month.
OLD_OLD_AMOUNTS= [Decimal(a) for a in ('0.00', '0.08', '0.16', '0.32', '0.64', '1.28')]
OLD_AMOUNTS= [Decimal(a) for a in ('0.25',)]

AMOUNTS = [Decimal(a) for a in ('0.00', '1.00', '3.00', '6.00', '12.00', '24.00')]


__version__ = "5.4.6"


def get_tip(tipper, tippee):
    """Given two user ids, return a Decimal.
    """
    TIP = """\

        SELECT amount
          FROM tips
         WHERE tipper=%s
           AND tippee=%s
      ORDER BY mtime DESC
         LIMIT 1

    """
    rec = db.fetchone(TIP, (tipper, tippee))
    if rec is None:
        tip = Decimal(0.00)
    else:
        tip = rec['amount']
    return tip


def get_dollars_receiving(participant_id):
    """Given a unicode, return a Decimal.
    """

    BACKED = """\

        SELECT sum(amount) AS dollars_receiving
          FROM ( SELECT DISTINCT ON (tipper)
                        amount
                      , tipper
                   FROM tips
                   JOIN participants p ON p.id = tipper
                  WHERE tippee=%s
                    AND last_bill_result = ''
                    AND is_suspicious IS NOT true
               ORDER BY tipper
                      , mtime DESC
                ) AS foo

    """
    rec = db.fetchone(BACKED, (participant_id,))
    if rec is None:
        amount = None
    else:
        amount = rec['dollars_receiving']  # might be None

    if amount is None:
        amount = Decimal('0.00')

    return amount


def get_dollars_giving(participant_id):
    """Given a unicode, return a Decimal.
    """

    BACKED = """\

        SELECT sum(amount) AS dollars_giving
          FROM ( SELECT DISTINCT ON (tippee)
                        amount
                      , tippee
                   FROM tips
                   JOIN participants p ON p.id = tippee
                  WHERE tipper=%s
                    AND last_bill_result = ''
                    AND is_suspicious IS NOT true
               ORDER BY tippee
                      , mtime DESC
                ) AS foo

    """
    rec = db.fetchone(BACKED, (participant_id,))
    if rec is None:
        amount = None
    else:
        amount = rec['dollars_giving']  # might be None

    if amount is None:
        amount = Decimal('0.00')

    return amount


def get_number_of_backers(participant_id):
    """Given a unicode, return an int.
    """

    BACKED = """\

        SELECT count(amount) AS nbackers
          FROM ( SELECT DISTINCT ON (tipper)
                        amount
                      , tipper
                   FROM tips
                   JOIN participants p ON p.id = tipper
                  WHERE tippee=%s
                    AND last_bill_result = ''
                    AND is_suspicious IS NOT true
               ORDER BY tipper
                      , mtime DESC
                ) AS foo
         WHERE amount > 0

    """
    rec = db.fetchone(BACKED, (participant_id,))
    if rec is None:
        nbackers = None
    else:
        nbackers = rec['nbackers']  # might be None

    if nbackers is None:
        nbackers = 0

    return nbackers


def get_chart_of_giving(user):
    SQL = """

        SELECT amount
             , count(amount) AS ncontributing
          FROM ( SELECT DISTINCT ON (tipper)
                        amount
                      , tipper
                   FROM tips
                   JOIN participants p ON p.id = tipper
                  WHERE tippee=%s
                    AND last_bill_result = ''
                    AND is_suspicious IS NOT true
               ORDER BY tipper
                      , mtime DESC
                ) AS foo
         WHERE amount > 0
      GROUP BY amount
      ORDER BY amount

    """
    npatrons = 0.0  # float to trigger float division
    contributed = Decimal('0.00')
    other = [-1, 0, 0]  # accumulates old tip amounts
    out = []
    for rec in db.fetchall(SQL, (user,)):
        if rec['amount'] not in AMOUNTS:
            other[1] += rec['ncontributing']
            other[2] += rec['amount'] * rec['ncontributing']
            contributed += rec['amount'] * rec['ncontributing']
        else:
            out.append([ rec['amount']
                       , rec['ncontributing']
                       , rec['amount'] * rec['ncontributing']
                        ])
            contributed += out[-1][2]
        npatrons += rec['ncontributing']
    if other != [-1, 0, 0]:
        out.append(other)
    for row in out:
        row.append((row[1] / npatrons) if npatrons > 0 else 0)
        row.append((row[2] / contributed) if contributed > 0 else 0)
    return out, npatrons, contributed


def get_giving_for_profile(tipper, db=None):
    """Given a participant id and a date, return a list and a Decimal.

    This function is used to populate a participant's page for their own
    viewing pleasure.

    A half-injected dependency, that's what db is.

    """
    if db is None:
        from gittip import db

    TIPS = """\

        SELECT * FROM (
            SELECT DISTINCT ON (tippee)
                   amount
                 , tippee
                 , t.ctime
                 , p.claimed_time
              FROM tips t
              JOIN participants p ON p.id = t.tippee
             WHERE tipper = %s
               AND p.is_suspicious IS NOT true
               AND p.claimed_time IS NOT NULL
          ORDER BY tippee
                 , t.mtime DESC
        ) AS foo
        ORDER BY amount DESC
               , tippee

    """
    tips = list(db.fetchall(TIPS, (tipper,)))


    # Compute the total.
    # ==================
    # For payday we only want to process payments to tippees who have
    # themselves opted into Gittip. For the tipper's profile page we want to
    # show the total amount they've pledged (so they're not surprised when
    # someone *does* start accepting tips and all of a sudden they're hit with
    # bigger charges.

    to_total = tips
    total = sum([t['amount'] for t in to_total])

    if not total:
        # If to_total is an empty list then total is int 0. We want a Decimal.
        total = Decimal('0.00')

    return tips, total


def get_tips_and_total(tipper, for_payday=False, db=None):
    """Given a participant id and a date, return a list and a Decimal.

    This function is used by the payday function. If for_payday is not False it
    must be a date object. Originally we also used this function to populate
    the profile page, but our requirements there changed while, oddly, our
    requirements in payday *also* changed to match the old requirements of the
    profile page. So this function keeps the for_payday parameter after all.

    A half-injected dependency, that's what db is.

    """
    if db is None:
        from gittip import db

    if for_payday:

        # For payday we want the oldest relationship to be paid first.
        order_by = "ctime ASC"


        # This is where it gets crash-proof.
        # ==================================
        # We need to account for the fact that we may have crashed during
        # Payday and we're re-running that function. We only want to select
        # tips that existed before Payday started, but haven't been processed
        # as part of this Payday yet.
        #
        # It's a bug if the paydays subselect returns > 1 rows.
        #
        # XXX If we crash during Payday and we rerun it after a timezone
        # change, will we get burned? How?

        ts_filter = """\

               AND mtime < %s
               AND ( SELECT id
                       FROM transfers
                      WHERE tipper=t.tipper
                        AND tippee=t.tippee
                        AND timestamp >= %s
                    ) IS NULL

        """
        args = (tipper, for_payday, for_payday)
    else:
        order_by = "amount DESC"
        ts_filter = ""
        args = (tipper,)

    TIPS = """\

        SELECT * FROM (
            SELECT DISTINCT ON (tippee)
                   amount
                 , tippee
                 , t.ctime
                 , p.claimed_time
              FROM tips t
              JOIN participants p ON p.id = t.tippee
             WHERE tipper = %%s
               AND p.is_suspicious IS NOT true
               %s
          ORDER BY tippee
                 , t.mtime DESC
        ) AS foo
        ORDER BY %s
               , tippee

    """ % (ts_filter, order_by)  # XXX, No injections here, right?!
    tips = list(db.fetchall(TIPS, args))


    # Compute the total.
    # ==================
    # For payday we only want to process payments to tippees who have
    # themselves opted into Gittip. For the tipper's profile page we want to
    # show the total amount they've pledged (so they're not surprised when
    # someone *does* start accepting tips and all of a sudden they're hit with
    # bigger charges.

    if for_payday:
        to_total = [t for t in tips if t['claimed_time'] is not None]
    else:
        to_total = tips
    total = sum([t['amount'] for t in to_total])

    if not total:
        # If to_total is an empty list then total is int 0. We want a Decimal.
        total = Decimal('0.00')

    return tips, total


# canonizer
# =========
# This is an Aspen hook to ensure that requests are served on a certain root
# URL, even if multiple domains point to the application.

class X: pass
canonical_scheme = None
canonical_host = None

def canonize(request):
    """Enforce a certain scheme and hostname. Store these on request as well.
    """
    scheme = request.headers.get('X-Forwarded-Proto', 'http') # per Heroku
    host = request.headers['Host']
    bad_scheme = scheme != canonical_scheme
    bad_host = bool(canonical_host) and (host != canonical_host)
                # '' and False => ''
    if bad_scheme or bad_host:
        url = '%s://%s' % (canonical_scheme, canonical_host)
        if request.line.method in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            # Redirect to a particular path for idempotent methods.
            url += request.line.uri.path.raw
            if request.line.uri.querystring:
                url += '?' + request.line.uri.querystring.raw
        else:
            # For non-idempotent methods, redirect to homepage.
            url += '/'
        request.redirect(url, permanent=True)


def configure_payments(request):
    # Work-around for https://github.com/balanced/balanced-python/issues/5
    import balanced
    balanced.configure(os.environ['BALANCED_API_SECRET'])
