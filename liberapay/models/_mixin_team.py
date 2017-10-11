"""Teams are groups of participants.
"""
from __future__ import division, print_function, unicode_literals

from collections import OrderedDict
from decimal import Decimal
from statistics import median

from liberapay.constants import D_INF, D_UNIT, D_ZERO
from liberapay.utils import NS


class MemberLimitReached(Exception): pass


class InactiveParticipantAdded(Exception): pass


class MixinTeam(object):

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
        self.set_take_for(member, D_ZERO, self, cursor=cursor)

    def remove_all_members(self, cursor=None):
        (cursor or self.db).run("""
            INSERT INTO takes
                        (ctime, member, team, amount, actual_amount, recorder)
                 SELECT ctime, member, %(id)s, NULL, NULL, %(id)s
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
        takes = {t.member: t.amount for t in self.db.all("""

            SELECT DISTINCT ON (member) member, amount, mtime
              FROM takes
             WHERE team=%s
               AND mtime < (
                       SELECT ts_start
                         FROM paydays
                        WHERE ts_end > ts_start
                     ORDER BY ts_start DESC LIMIT 1
                   )
          ORDER BY member, mtime DESC

        """, (self.id,)) if t.amount}
        return takes

    def get_take_for(self, member):
        """Return the nominal take for this member, or None.
        """
        return self.db.one(
            "SELECT amount FROM current_takes WHERE member = %s AND team = %s",
            (member.id, self.id)
        )

    def compute_max_this_week(self, member_id, last_week):
        """2x the member's take last week, or the member's take last week + the
        leftover, or last week's median take, or 1.00, or infinity if the takes
        were all zero last week or if throttling is disabled.
        """
        if not self.throttle_takes:
            return D_INF
        sum_last_week = sum(last_week.values())
        if sum_last_week == 0:
            return D_INF
        initial_leftover = self.receiving - sum_last_week
        nonzero_last_week = [a for a in last_week.values() if a]
        member_last_week = last_week.get(member_id, 0)
        return max(
            member_last_week * 2,
            member_last_week + initial_leftover,
            median(nonzero_last_week or (0,)),
            D_UNIT
        )

    def set_take_for(self, member, take, recorder, check_max=True, cursor=None):
        """Sets member's take from the team pool.
        """
        assert self.kind == 'group'

        if recorder.id != self.id:
            cur_take = self.get_take_for(member)
            if cur_take is None:
                return None

        if not isinstance(take, (None.__class__, Decimal)):
            take = Decimal(take)

        with self.db.get_cursor(cursor) as cursor:
            # Lock to avoid race conditions
            cursor.run("LOCK TABLE takes IN EXCLUSIVE MODE")
            # Throttle the new take, if there is more than one member
            if take and check_max and self.nmembers > 1 and take > 1:
                last_week = self.get_takes_last_week()
                max_this_week = self.compute_max_this_week(member.id, last_week)
                if take > max_this_week:
                    take = max_this_week
            # Insert the new take
            cursor.run("""

                INSERT INTO takes
                            (ctime, member, team, amount, actual_amount, recorder)
                     SELECT COALESCE((
                                SELECT ctime
                                  FROM takes
                                 WHERE member=%(member)s
                                   AND team=%(team)s
                                 LIMIT 1
                            ), current_timestamp)
                          , %(member)s
                          , %(team)s
                          , %(amount)s
                          , CASE WHEN %(amount)s IS NULL THEN NULL ELSE
                                COALESCE((
                                    SELECT actual_amount
                                      FROM takes
                                     WHERE member=%(member)s
                                       AND team=%(team)s
                                  ORDER BY mtime DESC
                                     LIMIT 1
                                ), 0)
                            END
                          , %(recorder)s

            """, dict(member=member.id, team=self.id, amount=take,
                      recorder=recorder.id))
            # Recompute the actual takes and update the cached amounts
            self.recompute_actual_takes(cursor, member=member)
            # Update is_funded on member's tips
            member.update_giving(cursor)

        return take

    def get_current_takes(self, cursor=None):
        """Return a list of member takes for a team.
        """
        assert self.kind == 'group'
        TAKES = """
            SELECT p.id AS member_id, p.username AS member_name, p.avatar_url
                 , (p.mangopay_user_id IS NOT NULL) AS is_identified
                 , t.amount, t.actual_amount, t.ctime, t.mtime
              FROM current_takes t
              JOIN participants p ON p.id = member
             WHERE t.team=%(team)s
          ORDER BY p.username
        """
        records = (cursor or self.db).all(TAKES, dict(team=self.id))
        return [r._asdict() for r in records]

    def recompute_actual_takes(self, cursor, member=None):
        """Get the tips and takes for this team and recompute the actual amounts.
        """
        from liberapay.billing.payday import Payday
        tips = [NS(t._asdict()) for t in cursor.all("""
            SELECT t.id, t.tipper, t.amount AS full_amount
                 , COALESCE((
                       SELECT sum(tr.amount)
                         FROM transfers tr
                        WHERE tr.tipper = t.tipper
                          AND tr.team = %(team_id)s
                          AND tr.context = 'take'
                          AND tr.status = 'succeeded'
                   ), 0) AS past_transfers_sum
              FROM current_tips t
             WHERE t.tippee = %(team_id)s
               AND t.is_funded
        """, dict(team_id=self.id))]
        takes = [NS(r._asdict()) for r in (cursor or self.db).all("""
            SELECT *
              FROM current_takes
             WHERE team = %s
        """, (self.id,))]
        # Recompute the takes
        takes_sum = {}
        transfers, new_leftover = Payday.resolve_takes(tips, takes)
        for t in transfers:
            if t.member in takes_sum:
                takes_sum[t.member] += t.amount
            else:
                takes_sum[t.member] = t.amount
        # Update the leftover
        cursor.run("UPDATE participants SET leftover = %s WHERE id = %s",
                   (new_leftover, self.id))
        self.set_attributes(leftover=new_leftover)
        # Update the cached amounts (actual_amount, taking, and receiving)
        for take in takes:
            member_id = take.member
            old_amount = take.actual_amount or D_ZERO
            new_amount = takes_sum.get(take.member, D_ZERO)
            diff = new_amount - old_amount
            if diff != 0:
                take.actual_amount = new_amount
                cursor.run("""
                    UPDATE takes
                       SET actual_amount = %(actual_amount)s
                     WHERE id = %(id)s
                """, take.__dict__)
                cursor.run("""
                    UPDATE participants
                       SET taking = (taking + %(diff)s)
                         , receiving = (receiving + %(diff)s)
                     WHERE id=%(member_id)s
                """, dict(member_id=member_id, diff=diff))
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
        takes = self.get_current_takes()
        last_week = self.get_takes_last_week()
        members = OrderedDict()
        members.leftover = self.leftover
        for take in takes:
            member = {}
            m_id = member['id'] = take['member_id']
            member['username'] = take['member_name']
            member['nominal_take'] = take['amount']
            member['actual_amount'] = take['actual_amount']
            member['last_week'] = last_week.get(m_id, D_ZERO)
            x = self.compute_max_this_week(m_id, last_week)
            member['max_this_week'] = x if x.is_finite() else None
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
