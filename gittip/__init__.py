from decimal import Decimal


db = None # This global is wired in wireup. It's an instance of 
          # gittip.postgres.PostgresManager.
AMOUNTS= [Decimal(a) for a in ('0.00', '0.08', '0.16', '0.32', '0.64', '1.28')]


__version__ = "~~VERSION~~"


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


def get_tipjar(participant_id):
    """Given a participant id, return a unicode.
    """
    TIPJAR = """\

        SELECT sum(amount) AS tipjar
          FROM ( SELECT DISTINCT ON (tipper)
                        amount
                      , tipper
                   FROM tips
                  WHERE tippee=%s
               ORDER BY tipper
                      , mtime DESC
                ) AS foo

    """
    rec = db.fetchone(TIPJAR, (participant_id,))
    if rec is None:
        tipjar = None
    else:
        tipjar = rec['tipjar']  # might be None
    if tipjar is None:
        tipjar = Decimal(0.00)

    if tipjar == 0:
        tipjar = u"an empty tipjar."
    elif tipjar < Decimal('5.12'):
        tipjar = u"a few tips pledged."
    else:
        tipjar = u"$%s pledged." % tipjar

    return tipjar


def get_tips_and_total(tipper, for_payday=False):
    """Given a participant id, return a list and a Decimal.

    This function is used to populate a participant's page for their own
    viewing pleasure, and also by the payday function.

    """
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
                      WHERE tipper=tips.tipper
                        AND tippee=tips.tippee
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
                 , ctime
              FROM tips
             WHERE tipper = %%s
               %s
          ORDER BY tippee
                 , mtime DESC
        ) AS foo
        ORDER BY %s
               , tippee

    """ % (ts_filter, order_by)
    tips = list(db.fetchall(TIPS, args))
    total = sum([tip['amount'] for tip in tips])
    if not total:
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
        url = '%s://%s/' % (canonical_scheme, canonical_host)
        request.redirect(url, permanent=True)
