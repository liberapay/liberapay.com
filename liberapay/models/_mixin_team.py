"""Teams are groups of participants.
"""
from __future__ import division, print_function, unicode_literals

from collections import OrderedDict
from decimal import Decimal, ROUND_UP
from statistics import median


ZERO = Decimal('0.00')
CENT = Decimal('0.01')
UNIT = Decimal('1.00')


class MemberLimitReached(Exception): pass


class InactiveParticipantAdded(Exception): pass


class MixinTeam(object):

    def invite(self, invitee, inviter):
        with self.db.get_cursor() as c:
            self.add_event(c, 'invite', dict(invitee=invitee.id), inviter.id)
            invitee.notify(
                'team_invite',
                team=self.username,
                team_url=self.url(),
                inviter=inviter.username,
            )

    def add_member(self, member, cursor=None):
        """Add a member to this team.
        """
        if len(self.get_current_takes()) == 149:
            raise MemberLimitReached
        if member.status != 'active':
            raise InactiveParticipantAdded
        self.set_take_for(member, ZERO, self, cursor=cursor)

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

            SELECT DISTINCT (member) member, amount, mtime
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
        takes['_relative_min'] = median(takes.values() or (0,)) ** Decimal('0.7')
        return takes

    def get_take_for(self, member):
        """Return a Decimal representation of the take for this member, or 0.
        """
        assert self.kind == 'group'
        return self.db.one( "SELECT amount FROM current_takes "
                            "WHERE member=%s AND team=%s"
                          , (member.id, self.id)
                          , default=ZERO
                           )

    def compute_max_this_week(self, member_id, last_week):
        """2x the member's take last week, or a minimum based on last week's
        median take, or current income divided by the number of members if takes
        were zero last week, or 1.
        """
        return max(
            last_week.get(member_id, 0) * 2,
            last_week['_relative_min'] or self.receiving / self.nmembers,
            UNIT
        )

    def set_take_for(self, member, take, recorder, check_max=True, cursor=None):
        """Sets member's take from the team pool.
        """
        assert self.kind == 'group'

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
            old = old_takes.get(p_id, {}).get('actual_amount', ZERO)
            new = new_takes.get(p_id, {}).get('actual_amount', ZERO)
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
            SELECT p.id AS member_id, p.username AS member_name, t.amount, t.ctime, t.mtime, p.avatar_url
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
        total_takes = sum(t['amount'] for t in nominal_takes)
        ratio = balance / total_takes if total_takes else 0
        for take in nominal_takes:
            nominal = take['nominal_take'] = take.pop('amount')
            actual = take['actual_amount'] = (nominal * ratio).quantize(CENT, rounding=ROUND_UP)
            balance -= actual
            actual_takes[take['member_id']] = take
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
        for take in takes.values():
            member = {}
            m_id = member['id'] = take['member_id']
            member['username'] = take['member_name']
            member['nominal_take'] = take['nominal_take']
            member['actual_amount'] = take['actual_amount']
            member['last_week'] = last_week.get(m_id, ZERO)
            member['max_this_week'] = self.compute_max_this_week(m_id, last_week)
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
