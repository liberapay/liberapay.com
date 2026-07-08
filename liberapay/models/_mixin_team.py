"""Teams are groups of participants.
"""

from collections import OrderedDict
from statistics import median

from liberapay.billing.payday import Payday
from liberapay.constants import TAKE_THROTTLING_THRESHOLD
from liberapay.i18n.currencies import Money, MoneyBasket
from liberapay.utils import group_by


class MemberLimitReached(Exception): pass


class InactiveParticipantAdded(Exception): pass


class MixinTeam:

    def invite(self, invitee, inviter):
        assert self.kind == 'group'
        with self.db.get_cursor() as c:
            n_id = invitee.notify(
                'team_invite',
                team=self.username,
                team_url=self.url(),
                inviter=inviter.username,
            )
            payload = dict(invitee=invitee.id, notification_id=n_id)
            self.add_event(c, 'invite', payload, inviter.id)

    def add_member(self, member, cursor=None):
        """Add a member to this team.
        """
        if self.nmembers >= 149:
            raise MemberLimitReached
        if member.status != 'active':
            raise InactiveParticipantAdded
        n_auto_takes, n_manual_takes = (cursor or self.db).one("""
            SELECT count(*) FILTER (WHERE t.amount < 0) AS n_auto_takes
                 , count(*) FILTER (WHERE t.amount >= 0) AS n_manual_takes
              FROM current_takes t
             WHERE t.team = %s
        """, (self.id,), default=(0, 0))
        if n_auto_takes == 0 and n_manual_takes > 0:
            # If the team only has manual takes, then the new member should
            # start at zero instead of taking all the leftover.
            initial_take = Money.ZEROS[member.main_currency]
        else:
            initial_take = Money(-1, member.main_currency)
        self.set_take_for(member, initial_take, self, cursor=cursor)

    def remove_all_members(self, cursor=None):
        (cursor or self.db).run("""
            INSERT INTO takes
                        (ctime, member, team, amount, actual_amount, recorder, paid_in_advance)
                 SELECT ctime, member, %(id)s, NULL, NULL, %(id)s, paid_in_advance
                   FROM current_takes
                  WHERE team=%(id)s
        """, dict(id=self.id))

    def member_of(self, team):
        """Given a Participant object, return a boolean.
        """
        assert team.kind == 'group'
        return self.db.one("""
            SELECT true
              FROM current_takes
             WHERE team=%s AND member=%s
        """, (team.id, self.id), default=False)

    def get_takes_last_week(self):
        """Get the users' nominal takes last week. Used in throttling.
        """
        assert self.kind == 'group'
        takes = OrderedDict((t.member, t.amount) for t in self.db.all("""

            SELECT DISTINCT ON (member) member, amount
              FROM takes
             WHERE team=%s
               AND mtime < (
                       SELECT ts_start
                         FROM paydays
                        WHERE ts_end > ts_start
                     ORDER BY ts_start DESC LIMIT 1
                   )
          ORDER BY member, mtime DESC

        """, (self.id,)) if t.amount is not None)
        takes.nonzero = any(amount != 0 for amount in takes.values())
        takes.sum = MoneyBasket(amount for amount in takes.values() if amount > 0)
        takes.initial_leftover = self.receiving - takes.sum.fuzzy_sum(self.main_currency)
        return takes

    def get_take_for(self, member):
        """Return the nominal take for this member, or None.
        """
        return self.db.one(
            "SELECT amount FROM current_takes WHERE member = %s AND team = %s",
            (member.id, self.id)
        )

    def compute_max_this_week(self, member_id, last_week, currency):
        """2x the member's take last week, or the member's take last week + the
        leftover, or last week's median take, or one currency unit (e.g. €1.00).
        """
        nonzero_last_week = [a.convert(currency).amount for a in last_week.values() if a]
        member_last_week = last_week.get(member_id, Money.ZEROS[currency]).convert(currency)
        return max(
            member_last_week * 2,
            member_last_week + last_week.initial_leftover.convert(currency),
            Money(median(nonzero_last_week or (0,)), currency),
            TAKE_THROTTLING_THRESHOLD[currency]
        )

    def set_take_for(self, member, take, recorder, check_max=True, cursor=None):
        """Sets member's take from the team pool.
        """
        assert self.kind == 'group'

        if recorder.id != self.id:
            cur_take = self.get_take_for(member)
            if cur_take is None:
                return None

        assert isinstance(take, (None.__class__, Money))
        if take is not None:
            take = take.convert_if_currency_is_phased_out()

        with self.db.get_cursor(cursor) as cursor:
            # Lock to avoid race conditions
            cursor.run("LOCK TABLE takes IN EXCLUSIVE MODE")
            # Throttle the new take, if there is more than one member
            if take and check_max and self.throttle_takes and self.nmembers > 1:
                if take > TAKE_THROTTLING_THRESHOLD[take.currency]:
                    last_week = self.get_takes_last_week()
                    if last_week.nonzero:
                        max_this_week = self.compute_max_this_week(
                            member.id, last_week, take.currency
                        )
                        if take > max_this_week:
                            take = max_this_week
            # Insert the new take
            cursor.run("""

                WITH old_take AS (
                         SELECT *
                           FROM takes
                          WHERE team = %(team)s
                            AND member = %(member)s
                       ORDER BY mtime DESC
                          LIMIT 1
                     )
                INSERT INTO takes
                            (ctime, member, team, amount, actual_amount, recorder, paid_in_advance)
                     SELECT COALESCE((
                                SELECT ctime
                                  FROM old_take
                            ), current_timestamp)
                          , %(member)s
                          , %(team)s
                          , %(amount)s
                          , CASE WHEN %(amount)s IS NULL THEN NULL ELSE
                                coalesce_currency_basket((
                                    SELECT actual_amount
                                      FROM old_take
                                ))
                            END
                          , %(recorder)s
                          , ( SELECT convert(
                                  paid_in_advance,
                                  COALESCE(%(amount)s::currency, paid_in_advance::currency)
                              ) FROM old_take )

            """, dict(member=member.id, team=self.id, amount=take,
                      recorder=recorder.id))
            # Recompute the actual takes and update the cached amounts
            self.recompute_actual_takes(cursor, member=member)
            # Close or reopen the team if necessary
            nmembers = cursor.one("""
                SELECT count(*)
                  FROM current_takes
                 WHERE team = %s
            """, (self.id,))
            if nmembers == 0:
                self.update_status('closed', cursor=cursor)
            elif self.status == 'closed':
                self.update_status('active', cursor=cursor)

        return take

    def remove_member(self, member, admin):
        """Forcibly remove a member from a team.
        """
        assert admin.has_privilege('admin')
        self.set_take_for(member, None, admin)

    def get_current_takes_for_display(self, cursor=None):
        """Return a list of member takes for a team.
        """
        assert self.kind == 'group'
        TAKES = """
            SELECT p.id AS member_id, p.username AS member_name, p.avatar_url
                 , p.is_suspended
                 , t.amount, t.actual_amount, t.ctime, t.mtime, t.paid_in_advance
              FROM current_takes t
              JOIN participants p ON p.id = member
             WHERE t.team=%(team)s
          ORDER BY p.username
        """
        return (cursor or self.db).all(TAKES, dict(team=self.id))

    def get_current_takes_for_payment(self, currency, tip):
        """
        Return the list of current takes with the extra information that the
        `liberapay.payin.common.resolve_team_donation` function needs to compute
        transfer amounts.
        """
        takes = self.db.all("""
            SELECT t.member, t.ctime, t.amount AS nominal_amount, t.paid_in_advance
                 , p.is_suspended
              FROM current_takes t
              JOIN participants p ON p.id = t.member
             WHERE t.team = %(team_id)s
        """, dict(currency=currency, team_id=self.id))
        zero = Money.ZEROS[currency]
        income_amount = self.receiving.convert(currency)
        if not tip.is_funded:
            income_amount += tip.amount.convert(currency)
        if income_amount == 0:
            income_amount = Money.MINIMUMS[currency]
        manual_takes_sum = MoneyBasket(t.nominal_amount for t in takes if t.nominal_amount > 0)
        n_auto_takes = sum(1 for t in takes if t.nominal_amount < 0) or 1
        auto_take = (
            (income_amount - manual_takes_sum.fuzzy_sum(currency)) /
            n_auto_takes
        ).round_up()
        if auto_take < 0:
            auto_take = zero
        for t in takes:
            t.paid_in_advance = (t.paid_in_advance or zero).convert(currency)
            t.naive_amount = \
                auto_take if t.nominal_amount < 0 else t.nominal_amount.convert(currency)
        return takes

    def recompute_actual_takes(self, cursor, member=None):
        """Get the tips and takes for this team and recompute the actual amounts.

        To avoid deadlocks the given `cursor` should have already acquired an
        exclusive lock on the `takes` table.
        """
        tips = cursor.all("""
            SELECT t.id, t.tipper, t.amount AS full_amount, t.paid_in_advance
                 , coalesce_currency_amount((
                       SELECT sum(tr.amount, t.amount::currency)
                         FROM transfers tr
                        WHERE tr.tipper = t.tipper
                          AND tr.team = %(team_id)s
                          AND tr.context IN ('take', 'partial-take', 'leftover-take')
                          AND tr.status = 'succeeded'
                   ), t.amount::currency) AS past_transfers_sum
              FROM current_tips t
              JOIN participants p ON p.id = t.tipper
             WHERE t.tippee = %(team_id)s
               AND ( t.is_funded OR t.paid_in_advance > 0 )
               AND p.is_suspended IS NOT true
        """, dict(team_id=self.id))
        takes = cursor.all("""
            SELECT t.*, p.main_currency, p.accepted_currencies
              FROM current_takes t
              JOIN participants p ON p.id = t.member
             WHERE t.team = %s
               AND p.is_suspended IS NOT true
        """, (self.id,))
        # Recompute the takes
        next_payday_id = cursor.one("""
            SELECT id
              FROM paydays
             WHERE ts_start IS NOT NULL
          ORDER BY id DESC
             LIMIT 1
        """, default=0) + 1
        transfers, new_leftover = Payday.resolve_takes(
            tips, takes, self.main_currency, next_payday_id,
        )
        transfers_by_member = group_by(transfers, lambda t: t.member)
        takes_sum = {k: MoneyBasket(t.amount for t in tr_list if not t.is_leftover)
                     for k, tr_list in transfers_by_member.items()}
        tippers = {k: set(t.tipper for t in tr_list)
                   for k, tr_list in transfers_by_member.items()}
        # Update the leftover
        cursor.run("UPDATE participants SET leftover = %s WHERE id = %s",
                   (new_leftover, self.id))
        self.set_attributes(leftover=new_leftover)
        # Update the cached amounts (actual_amount, taking, and receiving)
        zero = MoneyBasket()
        for take in takes:
            member_id = take.member
            old_amount = take.actual_amount or zero
            new_amount = takes_sum.get(take.member, zero)
            diff = new_amount - old_amount
            if diff != 0:
                take.actual_amount = new_amount
                cursor.run("""
                    UPDATE takes
                       SET actual_amount = %(actual_amount)s
                     WHERE id = %(id)s
                """, take.__dict__)
                ntippers = len(tippers.get(member_id, ()))
                member_currency, old_taking = cursor.one(
                    "SELECT main_currency, taking FROM participants WHERE id = %s", (member_id,)
                )
                diff = diff.fuzzy_sum(member_currency)
                if old_taking + diff < 0:
                    # Make sure currency fluctuation doesn't result in a negative number
                    diff = -old_taking
                cursor.run("""
                    UPDATE participants
                       SET taking = (taking + %(diff)s)
                         , receiving = (receiving + %(diff)s)
                         , nteampatrons = (
                               CASE WHEN (receiving + %(diff)s) = 0 THEN 0
                                    WHEN nteampatrons < %(ntippers)s THEN %(ntippers)s
                                    ELSE nteampatrons
                               END
                           )
                     WHERE id=%(member_id)s
                """, dict(member_id=member_id, diff=diff, ntippers=ntippers))
            if member and member.id == member_id:
                r = cursor.one(
                    "SELECT taking, receiving FROM participants WHERE id = %s",
                    (member_id,)
                )
                member.set_attributes(**r._asdict())
        return takes

    @property
    def nmembers(self):
        assert self.kind == 'group'
        return self.db.one("""
            SELECT COUNT(*)
              FROM current_takes
             WHERE team=%s
        """, (self.id,))

    def get_members(self):
        """Return an OrderedDict of member dicts.
        """
        takes = self.get_current_takes_for_display()
        takes.sort(key=lambda t: (
            -t['actual_amount'].fuzzy_sum(self.main_currency),
            t['member_name']
        ))
        nmembers = len(takes)
        last_week = self.get_takes_last_week()
        compute_max = self.throttle_takes and nmembers > 1 and last_week.nonzero
        members = OrderedDict()
        members.leftover = self.leftover or MoneyBasket()
        for take in takes:
            member = {}
            m_id = member['id'] = take['member_id']
            member['username'] = take['member_name']
            member['nominal_take'] = take['amount']
            member['actual_amount'] = take['actual_amount']
            member['received_in_advance'] = take['paid_in_advance']
            member['last_week'] = last_week.get(m_id)
            if compute_max:
                x = self.compute_max_this_week(m_id, last_week, take['amount'].currency)
            else:
                x = None
            member['max_this_week'] = x
            members[member['id']] = member
        return members

    @property
    def closed_by(self):
        assert self.status == 'closed'
        return self.db.one("""
            SELECT member
              FROM takes
             WHERE team = %s
          ORDER BY mtime DESC
             LIMIT 1
        """, (self.id,))
