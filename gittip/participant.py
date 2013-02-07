"""Defines a Participant class.
"""
import random
from decimal import Decimal

import gittip
from aspen import Response
from aspen.utils import typecheck
from psycopg2 import IntegrityError


ASCII_ALLOWED_IN_PARTICIPANT_ID = set("0123456789"
                                      "abcdefghijklmnopqrstuvwxyz"
                                      "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                                      ".,-_;:@ ")


class NoParticipantId(Exception):
    """Represent a bug where we treat an anonymous user as a participant.
    """


class NeedConfirmation(Exception):
    """We need confirmation before we'll proceed.
    """

    def __init__(self, a, b, c):
        self.other_is_a_real_participant = a
        self.this_is_others_last_account_elsewhere = b
        self.we_already_have_that_kind_of_account = c
        self._all = (a, b, c)

    def __repr__(self):
        return "<NeedConfirmation: %r %r %r>" % self._all
    __str__ = __repr__

    def __eq__(self, other):
        return self._all == other._all

    def __ne__(self, other):
        return not self.__eq__(other)

    def __nonzero__(self):
        # bool(need_confirmation)
        A, B, C = self._all
        return A or C


def gen_random_participant_ids():
    """Yield up to 100 random participant_ids.
    """
    seatbelt = 0
    while 1:
        yield hex(int(random.random() * 16**12))[2:].zfill(12).decode('ASCII')
        seatbelt += 1
        if seatbelt > 100:
            raise StopIteration


def reserve_a_random_participant_id(db=None):
    """Reserve and a random participant_id.

    The returned value is guaranteed to have been reserved in the database.

    """
    if db is None:  # During take_over we want to use our own transaction.
        db = gittip.db

    for participant_id in gen_random_participant_ids():
        try:
            db.execute( "INSERT INTO participants (id) VALUES (%s)"
                      , (participant_id,)
                       )
        except IntegrityError:  # Collision, try again with another value.
            pass
        else:
            break

    return participant_id


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

    class NoSelfTipping(Exception): pass
    class BadAmount(Exception): pass


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
                assert account['platform'] == 'twitter', account['platform']
                twitter_account = account
        return (github_account, twitter_account)


    @require_id
    def set_tip_to(self, tippee, amount):
        """Given participant id and amount as str, return amount as Decimal.

        We INSERT instead of UPDATE, so that we have history to explore. The
        COALESCE function returns the first of its arguments that is not NULL.
        The effect here is to stamp all tips with the timestamp of the first
        tip from this user to that. I believe this is used to determine the
        order of transfers during payday.

        """

        if self.id == tippee:
            raise self.NoSelfTipping

        amount = Decimal(amount)  # May raise InvalidOperation
        if amount not in gittip.AMOUNTS:
            raise self.BadAmount

        NEW_TIP = """\

            INSERT INTO tips
                        (ctime, tipper, tippee, amount)
                 VALUES ( COALESCE (( SELECT ctime
                                        FROM tips
                                       WHERE (tipper=%s AND tippee=%s)
                                       LIMIT 1
                                      ), CURRENT_TIMESTAMP)
                        , %s, %s, %s
                         )

        """
        gittip.db.execute( NEW_TIP
                         , (self.id, tippee, self.id, tippee, amount)
                          )
        return amount


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
            tip = Decimal('0.00')
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
                        AND is_suspicious IS NOT true
                        AND claimed_time IS NOT NULL
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
    def get_tip_distribution(self):
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

        UNCLAIMED_TIPS = """\

            SELECT * FROM (
                SELECT DISTINCT ON (tippee)
                       amount
                     , tippee
                     , t.ctime
                     , p.claimed_time
                     , e.platform
                     , e.user_info
                  FROM tips t
                  JOIN participants p ON p.id = t.tippee
                  JOIN elsewhere e ON e.participant_id = t.tippee
                 WHERE tipper = %s
                   AND p.is_suspicious IS NOT true
                   AND p.claimed_time IS NULL
              ORDER BY tippee
                     , t.mtime DESC
            ) AS foo
            ORDER BY amount DESC
                   , user_info->'screen_name'
                   , user_info->'login'

        """
        unclaimed_tips = list(db.fetchall(UNCLAIMED_TIPS, (self.id,)))


        # Compute the total.
        # ==================
        # For payday we only want to process payments to tippees who have
        # themselves opted into Gittip. For the tipper's profile page we want
        # to show the total amount they've pledged (so they're not surprised
        # when someone *does* start accepting tips and all of a sudden they're
        # hit with bigger charges.

        total = sum([t['amount'] for t in tips])
        if not total:
            # If tips is an empty list, total is int 0. We want a Decimal.
            total = Decimal('0.00')

        unclaimed_total = sum([t['amount'] for t in unclaimed_tips])
        if not unclaimed_total:
            unclaimed_total = Decimal('0.00')

        return tips, total, unclaimed_tips, unclaimed_total


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



    # Accounts Elsewhere
    # ==================

    @require_id
    def take_over(self, account_elsewhere, have_confirmation=False):
        """Given two unicodes, raise WontProceed or return None.

        This method associates an account on another platform (GitHub, Twitter,
        etc.) with the Gittip participant represented by self. Every account
        elsewhere has an associated Gittip participant account, even if its
        only a stub participant (it allows us to track pledges to that account
        should they ever decide to join Gittip).

        In certain circumstances, we want to present the user with a
        confirmation before proceeding to reconnect the account elsewhere to
        the new Gittip account; NeedConfirmation is the signal to request
        confirmation. If it was the last account elsewhere connected to the old
        Gittip account, then we absorb the old Gittip account into the new one,
        effectively archiving the old account.

        Here's what absorbing means:

            - consolidated tips to and fro are set up for the new participant

                Amounts are summed, so if alice tips bob $1 and carl $1, and
                then bob absorbs carl, then alice tips bob $2(!) and carl $0.

                And if bob tips alice $1 and carl tips alice $1, and then bob
                absorbs carl, then bob tips alice $2(!) and carl tips alice $0.

                The ctime of each new consolidated tip is the older of the two
                tips that are being consolidated.

                If alice tips bob $1, and alice absorbs bob, then alice tips
                bob $0.

                If alice tips bob $1, and bob absorbs alice, then alice tips
                bob $0.

            - all tips to and from the other participant are set to zero
            - the absorbed participant_id is released for reuse
            - the absorption is recorded in an absorptions table

        This is done in one transaction.

        """
        platform = account_elsewhere.platform
        user_id = account_elsewhere.user_id

        typecheck(platform, unicode, user_id, unicode, have_confirmation, bool)

        CONSOLIDATE_TIPS_RECEIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), tipper, %s AS tippee, sum(amount)
                   FROM (   SELECT DISTINCT ON (tipper, tippee)
                                   ctime, tipper, tippee, amount
                              FROM tips
                          ORDER BY tipper, tippee, mtime DESC
                         ) AS unique_tips
                  WHERE (tippee=%s OR tippee=%s)
                AND NOT (tipper=%s AND tippee=%s)
                AND NOT (tipper=%s)
               GROUP BY tipper

        """

        CONSOLIDATE_TIPS_GIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), %s AS tipper, tippee, sum(amount)
                   FROM (   SELECT DISTINCT ON (tipper, tippee)
                                   ctime, tipper, tippee, amount
                              FROM tips
                          ORDER BY tipper, tippee, mtime DESC
                         ) AS unique_tips
                  WHERE (tipper=%s OR tipper=%s)
                AND NOT (tipper=%s AND tippee=%s)
                AND NOT (tippee=%s)
               GROUP BY tippee

        """

        ZERO_OUT_OLD_TIPS_RECEIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT DISTINCT ON (tipper) ctime, tipper, tippee, 0 AS amount
                   FROM tips
                  WHERE tippee=%s

        """

        ZERO_OUT_OLD_TIPS_GIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT DISTINCT ON (tippee) ctime, tipper, tippee, 0 AS amount
                   FROM tips
                  WHERE tipper=%s

        """

        with gittip.db.get_transaction() as txn:

            # Load the existing connection.
            # =============================
            # Every account elsewhere has at least a stub participant account
            # on Gittip.

            txn.execute("""

                SELECT participant_id
                     , claimed_time IS NULL AS is_stub
                  FROM elsewhere
                  JOIN participants ON participant_id=participants.id
                 WHERE elsewhere.platform=%s AND elsewhere.user_id=%s

            """, (platform, user_id))
            rec = txn.fetchone()
            assert rec is not None          # sanity check

            other_id = rec['participant_id']


            # Make sure we have user confirmation if needed.
            # ==============================================
            # We need confirmation in whatever combination of the following
            # three cases:
            #
            #   - the other participant is not a stub; we are taking the
            #       account elsewhere away from another viable Gittip
            #       participant
            #
            #   - the other participant has no other accounts elsewhere; taking
            #       away the account elsewhere will leave the other Gittip
            #       participant without any means of logging in, and it will be
            #       archived and its tips absorbed by us
            #
            #   - we already have an account elsewhere connected from the given
            #       platform, and it will be handed off to a new stub
            #       participant

            # other_is_a_real_participant
            other_is_a_real_participant = not rec['is_stub']

            # this_is_others_last_account_elsewhere
            txn.execute( "SELECT count(*) AS nelsewhere FROM elsewhere "
                         "WHERE participant_id=%s"
                       , (other_id,)
                        )
            nelsewhere = txn.fetchone()['nelsewhere']
            assert nelsewhere > 0           # sanity check
            this_is_others_last_account_elsewhere = nelsewhere == 1

            # we_already_have_that_kind_of_account
            txn.execute( "SELECT count(*) AS nparticipants FROM elsewhere "
                         "WHERE participant_id=%s AND platform=%s"
                       , (self.id, platform)
                        )
            nparticipants = txn.fetchone()['nparticipants']
            assert nparticipants in (0, 1)  # sanity check
            we_already_have_that_kind_of_account = nparticipants == 1

            need_confirmation = NeedConfirmation( other_is_a_real_participant
                                                , this_is_others_last_account_elsewhere
                                                , we_already_have_that_kind_of_account
                                                 )
            if need_confirmation and not have_confirmation:
                raise need_confirmation


            # We have user confirmation. Proceed.
            # ===================================
            # There is a race condition here. The last person to call this will
            # win. XXX: I'm not sure what will happen to the DB and UI for the
            # loser.


            # Move any old account out of the way.
            # ====================================

            if we_already_have_that_kind_of_account:
                new_stub_id = reserve_a_random_participant_id(txn)
                txn.execute( "UPDATE elsewhere SET participant_id=%s "
                             "WHERE platform=%s AND participant_id=%s"
                           , (new_stub_id, platform, self.id)
                            )


            # Do the deal.
            # ============
            # If other_is_not_a_stub, then other will have the account
            # elsewhere taken away from them with this call. If there are other
            # browsing sessions open from that account, they will stay open
            # until they expire (XXX Is that okay?)

            txn.execute( "UPDATE elsewhere SET participant_id=%s "
                         "WHERE platform=%s AND user_id=%s"
                       , (self.id, platform, user_id)
                        )


            # Fold the old participant into the new as appropriate.
            # =====================================================
            # We want to do this whether or not other is a stub participant.

            if this_is_others_last_account_elsewhere:

                # Take over tips.
                # ===============

                x, y = self.id, other_id
                txn.execute(CONSOLIDATE_TIPS_RECEIVING, (x, x,y, x,y, x))
                txn.execute(CONSOLIDATE_TIPS_GIVING, (x, x,y, x,y, x))
                txn.execute(ZERO_OUT_OLD_TIPS_RECEIVING, (other_id,))
                txn.execute(ZERO_OUT_OLD_TIPS_GIVING, (other_id,))


                # Archive the old participant.
                # ============================
                # We always give them a new, random participant_id. We sign out
                # the old participant.

                for archive_id in gen_random_participant_ids():
                    try:
                        txn.execute("""

                            UPDATE participants
                               SET id=%s
                                 , session_token=NULL
                                 , session_expires=now()
                             WHERE id=%s
                         RETURNING id

                        """, (archive_id, other_id))
                        rec = txn.fetchone()
                    except IntegrityError:
                        continue  # archive_id is already taken; extremely
                                  # unlikely, but ...
                                  # XXX But can the UPDATE fail in other ways?
                    else:
                        assert rec is not None  # sanity checks
                        assert rec['id'] == archive_id
                        break


                # Record the absorption.
                # ======================
                # This is for preservation of history.

                txn.execute( "INSERT INTO absorptions "
                             "(absorbed_was, absorbed_by, archived_as) "
                             "VALUES (%s, %s, %s)"
                           , (other_id, self.id, archive_id)
                            )


            # Lastly, keep account_elsewhere in sync.
            # =======================================
            # Bandaid for
            #
            #   https://github.com/zetaweb/www.gittip.com/issues/421
            #
            # XXX This is why we're porting to SQLAlchemy:
            #
            #   https://github.com/zetaweb/www.gittip.com/issues/129

            account_elsewhere.participant_id = self.id
