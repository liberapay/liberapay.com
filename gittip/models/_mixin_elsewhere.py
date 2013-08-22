import os

from gittip import NotSane
from aspen.utils import typecheck
from psycopg2 import IntegrityError


# Exceptions
# ==========

class UnknownPlatform(Exception): pass

class NeedConfirmation(Exception):
    """Represent the case where we need user confirmation during a merge.

    This is used in the workflow for merging one participant into another.

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


# Mixin
# =====

class MixinElsewhere(object):
    """We use this as a mixin for Participant, and in a hackish way on the
    homepage and community pages.

    """

    def get_accounts_elsewhere(self):
        """Return a four-tuple of elsewhere Records.
        """
        github_account = None
        twitter_account = None
        bitbucket_account = None
        bountysource_account = None

        ACCOUNTS = "SELECT * FROM elsewhere WHERE participant=%s"
        accounts = self.db.all(ACCOUNTS, (self.username,))

        for account in accounts:
            if account.platform == "github":
                github_account = account
            elif account.platform == "twitter":
                twitter_account = account
            elif account.platform == "bitbucket":
                bitbucket_account = account
            elif account.platform == "bountysource":
                bountysource_account = account
            else:
                raise UnknownPlatform(account.platform)

        return ( github_account
               , twitter_account
               , bitbucket_account
               , bountysource_account
                )


    def get_img_src(self, size=128):
        """Return a value for <img src="..." />.

        Until we have our own profile pics, delegate. XXX Is this an attack
        vector? Can someone inject this value? Don't think so, but if you make
        it happen, let me know, eh? Thanks. :)

            https://www.gittip.com/security.txt

        """
        typecheck(size, int)

        src = '/assets/%s/avatar-default.gif' % os.environ['__VERSION__']

        github, twitter, bitbucket, bountysource = \
                                                  self.get_accounts_elsewhere()
        if github is not None:
            # GitHub -> Gravatar: http://en.gravatar.com/site/implement/images/
            if 'gravatar_id' in github.user_info:
                gravatar_hash = github.user_info['gravatar_id']
                src = "https://www.gravatar.com/avatar/%s.jpg?s=%s"
                src %= (gravatar_hash, size)

        elif twitter is not None:
            # https://dev.twitter.com/docs/api/1.1/get/users/show
            if 'profile_image_url_https' in twitter.user_info:
                src = twitter.user_info['profile_image_url_https']

                # For Twitter, we don't have good control over size. The
                # biggest option is 73px(?!), but that's too small. Let's go
                # with the original: even though it may be huge, that's
                # preferrable to guaranteed blurriness. :-/

                src = src.replace('_normal.', '.')

        return src


    def take_over(self, account_elsewhere, have_confirmation=False):
        """Given two objects and a bool, raise NeedConfirmation or return None.

        This method associates an account on another platform (GitHub, Twitter,
        etc.) with the given Gittip participant. Every account elsewhere has an
        associated Gittip participant account, even if its only a stub
        participant (it allows us to track pledges to that account should they
        ever decide to join Gittip).

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
            - the absorbed username is released for reuse
            - the absorption is recorded in an absorptions table

        This is done in one transaction.

        """
        # Lazy imports to dodge circular imports.
        from gittip.models.participant import reserve_a_random_username
        from gittip.models.participant import gen_random_usernames

        platform = account_elsewhere.platform
        user_id = account_elsewhere.user_id

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

        with self.db.get_cursor() as cursor:

            # Load the existing connection.
            # =============================
            # Every account elsewhere has at least a stub participant account
            # on Gittip.

            rec = cursor.one("""

                SELECT participant
                     , claimed_time IS NULL AS is_stub
                  FROM elsewhere
                  JOIN participants ON participant=participants.username
                 WHERE elsewhere.platform=%s AND elsewhere.user_id=%s

            """, (platform, user_id), default=NotSane)

            other_username = rec.participant


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
            other_is_a_real_participant = not rec.is_stub

            # this_is_others_last_account_elsewhere
            nelsewhere = cursor.one( "SELECT count(*) FROM elsewhere "
                                     "WHERE participant=%s"
                                   , (other_username,)
                                    )
            assert nelsewhere > 0           # sanity check
            this_is_others_last_account_elsewhere = (nelsewhere == 1)

            # we_already_have_that_kind_of_account
            nparticipants = cursor.one( "SELECT count(*) FROM elsewhere "
                                        "WHERE participant=%s AND platform=%s"
                                      , (self.username, platform)
                                       )
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
                new_stub_username = reserve_a_random_username(cursor)
                cursor.run( "UPDATE elsewhere SET participant=%s "
                            "WHERE platform=%s AND participant=%s"
                          , (new_stub_username, platform, self.username)
                           )


            # Do the deal.
            # ============
            # If other_is_not_a_stub, then other will have the account
            # elsewhere taken away from them with this call. If there are other
            # browsing sessions open from that account, they will stay open
            # until they expire (XXX Is that okay?)

            cursor.run( "UPDATE elsewhere SET participant=%s "
                        "WHERE platform=%s AND user_id=%s"
                      , (self.username, platform, user_id)
                       )


            # Fold the old participant into the new as appropriate.
            # =====================================================
            # We want to do this whether or not other is a stub participant.

            if this_is_others_last_account_elsewhere:

                # Take over tips.
                # ===============

                x, y = self.username, other_username
                cursor.run(CONSOLIDATE_TIPS_RECEIVING, (x, x,y, x,y, x))
                cursor.run(CONSOLIDATE_TIPS_GIVING, (x, x,y, x,y, x))
                cursor.run(ZERO_OUT_OLD_TIPS_RECEIVING, (other_username,))
                cursor.run(ZERO_OUT_OLD_TIPS_GIVING, (other_username,))


                # Archive the old participant.
                # ============================
                # We always give them a new, random username. We sign out
                # the old participant.

                for archive_username in gen_random_usernames():
                    try:
                        username = cursor.one("""

                            UPDATE participants
                               SET username=%s
                                 , username_lower=%s
                                 , session_token=NULL
                                 , session_expires=now()
                             WHERE username=%s
                         RETURNING username

                        """, ( archive_username
                             , archive_username.lower()
                             , other_username
                              ), default=NotSane)
                    except IntegrityError:
                        continue  # archive_username is already taken;
                                  # extremely unlikely, but ...
                                  # XXX But can the UPDATE fail in other ways?
                    else:
                        assert username == archive_username
                        break


                # Record the absorption.
                # ======================
                # This is for preservation of history.

                cursor.run( "INSERT INTO absorptions "
                            "(absorbed_was, absorbed_by, archived_as) "
                            "VALUES (%s, %s, %s)"
                          , ( other_username
                            , self.username
                            , archive_username
                             )
                           )

# Utter Hack
# ==========

def utter_hack(records):
    for rec in records:
        yield UtterHack(rec)

class UtterHack(MixinElsewhere):
    def __init__(self, rec):
        import gittip
        self.db = gittip.db
        for name in rec._fields:
            setattr(self, name, getattr(rec, name))
