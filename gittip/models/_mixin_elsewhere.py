import os
from collections import namedtuple

from gittip import NotSane
from aspen.utils import typecheck
from psycopg2 import IntegrityError

from gittip.exceptions import UnknownPlatform
from gittip.elsewhere import platform_classes
from gittip.utils.username import reserve_a_random_username, gen_random_usernames


# Exceptions
# ==========

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

# note that the ordering of these fields is defined by platform_classes
AccountsTuple = namedtuple('AccountsTuple', platform_classes.keys())

class MixinElsewhere(object):
    """We use this as a mixin for Participant, and in a hackish way on the
    homepage and community pages.

    """

    def get_accounts_elsewhere(self):
        """Return an AccountsTuple of AccountElsewhere instances.
        """

        ACCOUNTS = "SELECT * FROM elsewhere WHERE participant=%s"
        accounts = self.db.all(ACCOUNTS, (self.username,))

        accounts_dict = {platform: None for platform in platform_classes}

        for account in accounts:
            if account.platform not in platform_classes:
                raise UnknownPlatform(account.platform)

            account_cls = platform_classes[account.platform]
            accounts_dict[account.platform] = \
                account_cls(self.db, account.user_id, existing_record=account)

        return AccountsTuple(**accounts_dict)

    def get_img_src(self, size=128):
        """Return a value for <img src="..." />.

        Until we have our own profile pics, delegate. XXX Is this an attack
        vector? Can someone inject this value? Don't think so, but if you make
        it happen, let me know, eh? Thanks. :)

            https://www.gittip.com/security.txt

        """
        typecheck(size, int)

        src = '/assets/%s/avatar-default.gif' % os.environ['__VERSION__']

        accounts = self.get_accounts_elsewhere()

        if accounts.github is not None:
            # GitHub -> Gravatar: http://en.gravatar.com/site/implement/images/
            if 'gravatar_id' in accounts.github.user_info:
                gravatar_hash = accounts.github.user_info['gravatar_id']
                src = "https://www.gravatar.com/avatar/%s.jpg?s=%s"
                src %= (gravatar_hash, size)

        elif accounts.twitter is not None:
            # https://dev.twitter.com/docs/api/1.1/get/users/show
            if 'profile_image_url_https' in accounts.twitter.user_info:
                src = accounts.twitter.user_info['profile_image_url_https']

                # For Twitter, we don't have good control over size. The
                # biggest option is 73px(?!), but that's too small. Let's go
                # with the original: even though it may be huge, that's
                # preferrable to guaranteed blurriness. :-/

                src = src.replace('_normal.', '.')

        elif accounts.openstreetmap is not None:
            if 'img_src' in accounts.openstreetmap.user_info:
                src = accounts.openstreetmap.user_info['img_src']

        return src


    def take_over(self, account_elsewhere, have_confirmation=False):
        """Given an AccountElsewhere and a bool, raise NeedConfirmation or return None.

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

        platform = account_elsewhere.platform
        user_id = account_elsewhere.user_id

        CREATE_TEMP_TABLE_FOR_UNIQUE_TIPS = """

        CREATE TEMP TABLE __temp_unique_tips ON COMMIT drop AS

            -- Get all the latest tips from everyone to everyone.

            SELECT DISTINCT ON (tipper, tippee)
                   ctime, tipper, tippee, amount
              FROM tips
          ORDER BY tipper, tippee, mtime DESC;

        """

        CONSOLIDATE_TIPS_RECEIVING = """

            -- Create a new set of tips, one for each current tip *to* either
            -- the dead or the live account. If a user was tipping both the
            -- dead and the live account, then we create one new combined tip
            -- to the live account (via the GROUP BY and sum()).

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), tipper, %(live)s AS tippee, sum(amount)

                   FROM __temp_unique_tips

                  WHERE (tippee = %(dead)s OR tippee = %(live)s)
                        -- Include tips *to* either the dead or live account.

                AND NOT (tipper = %(dead)s OR tipper = %(live)s)
                        -- Don't include tips *from* the dead or live account,
                        -- lest we convert cross-tipping to self-tipping.

                    AND amount > 0
                        -- Don't include zeroed out tips, so we avoid a no-op
                        -- zero tip entry.

               GROUP BY tipper

        """

        CONSOLIDATE_TIPS_GIVING = """

            -- Create a new set of tips, one for each current tip *from* either
            -- the dead or the live account. If both the dead and the live
            -- account were tipping a given user, then we create one new
            -- combined tip from the live account (via the GROUP BY and sum()).

            INSERT INTO tips (ctime, tipper, tippee, amount)

                 SELECT min(ctime), %(live)s AS tipper, tippee, sum(amount)

                   FROM __temp_unique_tips

                  WHERE (tipper = %(dead)s OR tipper = %(live)s)
                        -- Include tips *from* either the dead or live account.

                AND NOT (tippee = %(dead)s OR tippee = %(live)s)
                        -- Don't include tips *to* the dead or live account,
                        -- lest we convert cross-tipping to self-tipping.

                    AND amount > 0
                        -- Don't include zeroed out tips, so we avoid a no-op
                        -- zero tip entry.

               GROUP BY tippee

        """

        ZERO_OUT_OLD_TIPS_RECEIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM __temp_unique_tips
                 WHERE tippee=%s AND amount > 0

        """

        ZERO_OUT_OLD_TIPS_GIVING = """

            INSERT INTO tips (ctime, tipper, tippee, amount)

                SELECT ctime, tipper, tippee, 0 AS amount
                  FROM __temp_unique_tips
                 WHERE tipper=%s AND amount > 0

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
                cursor.run(CREATE_TEMP_TABLE_FOR_UNIQUE_TIPS)
                cursor.run(CONSOLIDATE_TIPS_RECEIVING, dict(live=x, dead=y))
                cursor.run(CONSOLIDATE_TIPS_GIVING, dict(live=x, dead=y))
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

def utter_hack(db, records):
    for rec in records:
        yield UtterHack(db, rec)

class UtterHack(MixinElsewhere):
    def __init__(self, db, rec):
        self.db = db
        for name in rec._fields:
            setattr(self, name, getattr(rec, name))
