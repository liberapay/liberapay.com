"""Teams are groups of participants.
"""
from __future__ import division, print_function, unicode_literals

from collections import OrderedDict
from decimal import Decimal, ROUND_UP
from statistics import median

from liberapay.constants import D_CENT, D_INF, D_UNIT, D_ZERO


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
        if len(self.get_current_takes()) == 149:
            raise MemberLimitReached
        if member.status != 'active':
            raise InactiveParticipantAdded
        self.set_take_for(member, D_ZERO, self, cursor=cursor)

    def remove_all_members(self, cursor=None):
        (cursor or self.db).run("""
            INSERT INTO takes (ctime, member, team, amount, recorder) (
                SELECT ctime, member, %(id)s, NULL, %(id)s
                  FROM current_takes
                 WHERE team=%(id)s
            );
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
        """2x the member's take last week, or the member's take last week + a
        proportional share of the leftover, or a minimum based on last week's
        median take, or 1.
        """
        if not self.throttle_takes:
            return D_INF
        sum_last_week = sum(last_week.values())
        if sum_last_week == 0:
            return D_INF
        initial_leftover = self.receiving - sum_last_week
        nonzero_last_week = [a for a in last_week.values() if a]
        member_last_week = last_week.get(member_id, 0)
        leftover_share = member_last_week / (sum_last_week or D_INF)
        leftover_share = max(leftover_share, D_UNIT / self.nmembers)
        return max(
            member_last_week * 2,
            member_last_week + initial_leftover * leftover_share,
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

        if take and check_max and take > 1:
            last_week = self.get_takes_last_week()
            max_this_week = self.compute_max_this_week(member.id, last_week)
            if take > max_this_week:
                take = max_this_week

        with self.db.get_cursor(cursor) as cursor:
            # Lock to avoid race conditions
            cursor.run("LOCK TABLE takes IN EXCLUSIVE MODE")
            # Compute the current takes
            old_takes = self.compute_actual_takes(cursor)
            # Insert the new take
            cursor.run("""

                INSERT INTO takes (ctime, member, team, amount, recorder)
                 VALUES ( COALESCE (( SELECT ctime
                                        FROM takes
                                       WHERE member=%(member)s
                                         AND team=%(team)s
                                       LIMIT 1
                                     ), CURRENT_TIMESTAMP)
                        , %(member)s
                        , %(team)s
                        , %(amount)s
                        , %(recorder)s
                         )

            """, dict(member=member.id, team=self.id, amount=take,
                      recorder=recorder.id))
            # Compute the new takes
            new_takes = self.compute_actual_takes(cursor)
            # Update receiving amounts in the participants table
            self.update_taking(old_takes, new_takes, cursor, member)
            # Update is_funded on member's tips
            member.update_giving(cursor)

        return take

    def update_taking(self, old_takes, new_takes, cursor=None, member=None):
        """Update `taking` amounts based on the difference between `old_takes`
        and `new_takes`.
        """
        for p_id in set(old_takes.keys()).union(new_takes.keys()):
            old = old_takes.get(p_id, {}).get('actual_amount', D_ZERO)
            new = new_takes.get(p_id, {}).get('actual_amount', D_ZERO)
            diff = new - old
            if diff != 0:
                (cursor or self.db).run("""
                    UPDATE participants
                       SET taking = (taking + %(diff)s)
                         , receiving = (receiving + %(diff)s)
                     WHERE id=%(p_id)s
                """, dict(p_id=p_id, diff=diff))
            if member and p_id == member.id:
                r = (cursor or self.db).one(
                    "SELECT taking, receiving FROM participants WHERE id = %s",
                    (p_id,)
                )
                member.set_attributes(**r._asdict())

    def get_current_takes(self, cursor=None):
        """Return a list of member takes for a team.
        """
        assert self.kind == 'group'
        TAKES = """
            SELECT p.id AS member_id, p.username AS member_name, p.avatar_url
                 , (p.mangopay_user_id IS NOT NULL) AS is_identified
                 , t.amount, t.ctime, t.mtime
              FROM current_takes t
              JOIN participants p ON p.id = member
             WHERE t.team=%(team)s
          ORDER BY p.username
        """
        records = (cursor or self.db).all(TAKES, dict(team=self.id))
        return [r._asdict() for r in records]

    def compute_actual_takes(self, cursor=None):
        """Get the takes, compute the actual amounts, and return an OrderedDict.
        """
        actual_takes = OrderedDict()
        nominal_takes = self.get_current_takes(cursor=cursor)
        balance = self.receiving
        total_takes = sum(t['amount'] for t in nominal_takes if t['is_identified'])
        ratio = min(balance / total_takes, 1) if total_takes else 0
        for take in nominal_takes:
            nominal = take['nominal_take'] = take.pop('amount')
            actual = take['actual_amount'] = min(
                (nominal * ratio).quantize(D_CENT, rounding=ROUND_UP),
                balance
            ) if take['is_identified'] else D_ZERO
            balance -= actual
            actual_takes[take['member_id']] = take
        actual_takes.leftover = balance
        return actual_takes

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
        takes = self.compute_actual_takes()
        last_week = self.get_takes_last_week()
        members = OrderedDict()
        members.leftover = takes.leftover
        for take in takes.values():
            member = {}
            m_id = member['id'] = take['member_id']
            member['username'] = take['member_name']
            member['nominal_take'] = take['nominal_take']
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
