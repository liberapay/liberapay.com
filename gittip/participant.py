"""Defines a Participant class.
"""
from aspen import Response
from decimal import Decimal

import gittip
from aspen.utils import typecheck


ASCII_ALLOWED_IN_PARTICIPANT_ID = set("0123456789"
                                      "abcdefghijklmnopqrstuvwxyz"
                                      "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                      ".,-_;:@ ")


class NoParticipantId(StandardError):
    """Represent a bug where we treat an anonymous user as a participant.
    """


def require_id(func):
    # XXX This should be done with a metaclass, maybe?
    def wrapped(self, *a, **kw):
        if self.id is None:
            raise NoParticipantId("User does not participate, apparently.")
        return func(self, *a, **kw)
    return wrapped


class Participant(object):
    """Represent a Gittip participant.
    """

    def __init__(self, participant_id):
        typecheck(participant_id, (unicode, None))
        self.id = participant_id


    @require_id
    def get_details(self):
        """Return a dictionary.
        """
        SELECT = """

            SELECT *
              FROM participants
             WHERE id = %s

        """
        return gittip.db.fetchone(SELECT, (self.id,))


    # Claiming
    # ========
    # An unclaimed Participant is a stub that's created when someone pledges to
    # give to an AccountElsewhere that's not been connected on Gittip yet.

    @require_id
    def resolve_unclaimed(self):
        """Given a participant_id, return an URL path.
        """
        rec = gittip.db.fetchone("SELECT platform, user_info FROM elsewhere "
                                 "WHERE participant_id = %s", (self.id,))
        if rec is None:
            out = None
        elif rec['platform'] == 'github':
            out = '/on/github/%s/' % rec['user_info']['login']
        else:
            assert rec['platform'] == 'twitter'
            out = '/on/twitter/%s/' % rec['user_info']['screen_name']
        return out

    @require_id
    def set_as_claimed(self):
        CLAIM = """\

            UPDATE participants
               SET claimed_time=CURRENT_TIMESTAMP
             WHERE id=%s
               AND claimed_time IS NULL

        """
        gittip.db.execute(CLAIM, (self.id,))



    @require_id
    def change_id(self, suggested):
        """Raise Response or return None.

        We want to be pretty loose with usernames. Unicode is allowed--XXX
        aspen bug :(. So are spaces.Control characters aren't. We also limit to
        32 characters in length.

        """
        for i, c in enumerate(suggested):
            if i == 32:
                raise Response(413)  # Request Entity Too Large (more or less)
            elif ord(c) < 128 and c not in ASCII_ALLOWED_IN_PARTICIPANT_ID:
                raise Response(400)  # Yeah, no.
            elif c not in ASCII_ALLOWED_IN_PARTICIPANT_ID:
                raise Response(400)  # XXX Burned by an Aspen bug. :`-(
                                     # https://github.com/whit537/aspen/issues/102

        if suggested in gittip.RESTRICTED_IDS:
            raise Response(400)

        if suggested != self.id:
            # Will raise IntegrityError if the desired participant_id is taken.
            rec = gittip.db.fetchone("UPDATE participants "
                                     "SET id=%s WHERE id=%s "
                                     "RETURNING id", (suggested, self.id))

            assert rec is not None         # sanity check
            assert suggested == rec['id']  # sanity check
            self.id = suggested


    @require_id
    def get_accounts_elsewhere(self):
        """Return a two-tuple of elsewhere dicts.
        """
        ACCOUNTS = """
            SELECT * FROM elsewhere WHERE participant_id=%s;
        """
        accounts = gittip.db.fetchall(ACCOUNTS, (self.id,))
        assert accounts is not None
        twitter_account = None
        github_account = None
        for account in accounts:
            if account['platform'] == 'github':
                github_account = account
            else:
                assert account['platform'] == 'twitter'
                twitter_account = account
        return (github_account, twitter_account)


    @require_id
    def get_tip_to(self, tippee):
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
        rec = gittip.db.fetchone(TIP, (self.id, tippee))
        if rec is None:
            tip = Decimal(0.00)
        else:
            tip = rec['amount']
        return tip


    @require_id
    def get_dollars_receiving(self):
        """Return a Decimal.
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
        rec = gittip.db.fetchone(BACKED, (self.id,))
        if rec is None:
            amount = None
        else:
            amount = rec['dollars_receiving']  # might be None

        if amount is None:
            amount = Decimal('0.00')

        return amount


    @require_id
    def get_dollars_giving(self):
        """Return a Decimal.
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
        rec = gittip.db.fetchone(BACKED, (self.id,))
        if rec is None:
            amount = None
        else:
            amount = rec['dollars_giving']  # might be None

        if amount is None:
            amount = Decimal('0.00')

        return amount


    @require_id
    def get_number_of_backers(self):
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
        rec = gittip.db.fetchone(BACKED, (self.id,))
        if rec is None:
            nbackers = None
        else:
            nbackers = rec['nbackers']  # might be None

        if nbackers is None:
            nbackers = 0

        return nbackers


    @require_id
    def get_chart_of_receiving(self):
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
        for rec in gittip.db.fetchall(SQL, (self.id,)):
            if rec['amount'] not in gittip.AMOUNTS:
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


    @require_id
    def get_giving_for_profile(self, db=None):
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
        tips = list(db.fetchall(TIPS, (self.id,)))


        # Compute the total.
        # ==================
        # For payday we only want to process payments to tippees who have
        # themselves opted into Gittip. For the tipper's profile page we want
        # to show the total amount they've pledged (so they're not surprised
        # when someone *does* start accepting tips and all of a sudden they're
        # hit with bigger charges.

        to_total = tips
        total = sum([t['amount'] for t in to_total])

        if not total:
            # If to_total is an empty list, total is int 0. We want a Decimal.
            total = Decimal('0.00')

        return tips, total


    @require_id
    def get_tips_and_total(self, for_payday=False, db=None):
        """Given a participant id and a date, return a list and a Decimal.

        This function is used by the payday function. If for_payday is not
        False it must be a date object. Originally we also used this function
        to populate the profile page, but our requirements there changed while,
        oddly, our requirements in payday *also* changed to match the old
        requirements of the profile page. So this function keeps the for_payday
        parameter after all.

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
            # tips that existed before Payday started, but haven't been
            # processed as part of this Payday yet.
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
            args = (self.id, for_payday, for_payday)
        else:
            order_by = "amount DESC"
            ts_filter = ""
            args = (self.id,)

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
        # themselves opted into Gittip. For the tipper's profile page we want
        # to show the total amount they've pledged (so they're not surprised
        # when someone *does* start accepting tips and all of a sudden they're
        # hit with bigger charges.

        if for_payday:
            to_total = [t for t in tips if t['claimed_time'] is not None]
        else:
            to_total = tips
        total = sum([t['amount'] for t in to_total])

        if not total:
            # If to_total is an empty list, total is int 0. We want a Decimal.
            total = Decimal('0.00')

        return tips, total
