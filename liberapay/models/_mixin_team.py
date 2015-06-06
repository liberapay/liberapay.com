"""Teams are groups of participants.
"""
from collections import OrderedDict
from decimal import Decimal


class MemberLimitReached(Exception): pass


class InactiveParticipantAdded(Exception): pass


class MixinTeam(object):

    def add_member(self, member):
        """Add a member to this team.
        """
        if len(self.get_current_takes()) == 149:
            raise MemberLimitReached
        if member.status != 'active':
            raise InactiveParticipantAdded
        self.set_take_for(member, Decimal('0.00'), self)

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

    def get_take_last_week_for(self, member):
        """Get the user's nominal take last week. Used in throttling.
        """
        assert self.kind == 'group'
        member_id = getattr(member, 'id', None) or member['id']
        return self.db.one("""

            SELECT amount
              FROM takes
             WHERE team=%s AND member=%s
               AND mtime < (
                       SELECT ts_start
                         FROM paydays
                        WHERE ts_end > ts_start
                     ORDER BY ts_start DESC LIMIT 1
                   )
          ORDER BY mtime DESC LIMIT 1

        """, (self.id, member_id)) or Decimal('0.00')

    def get_take_for(self, member):
        """Return a Decimal representation of the take for this member, or 0.
        """
        assert self.kind == 'group'
        return self.db.one( "SELECT amount FROM current_takes "
                            "WHERE member=%s AND team=%s"
                          , (member.id, self.id)
                          , default=Decimal('0.00')
                           )

    def compute_max_this_week(self, last_week):
        """2x last week's take, but at least a dollar.
        """
        return max(last_week * Decimal('2'), Decimal('1.00'))

    def set_take_for(self, member, take, recorder, check_max=True, cursor=None):
        """Sets member's take from the team pool.
        """
        assert self.kind == 'group'

        if take and check_max:
            last_week = self.get_take_last_week_for(member)
            max_this_week = self.compute_max_this_week(last_week)
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
            if p_id == self.id:
                continue
            old = old_takes.get(p_id, {}).get('actual_amount', Decimal(0))
            new = new_takes.get(p_id, {}).get('actual_amount', Decimal(0))
            diff = new - old
            if diff != 0:
                r = (cursor or self.db).one("""
                    UPDATE participants
                       SET taking = (taking + %(diff)s)
                         , receiving = (receiving + %(diff)s)
                     WHERE id=%(p_id)s
                 RETURNING taking, receiving
                """, dict(p_id=p_id, diff=diff))
                if member and p_id == member.id:
                    member.set_attributes(**r._asdict())

    def get_current_takes(self, cursor=None):
        """Return a list of member takes for a team.
        """
        assert self.kind == 'group'
        TAKES = """
            SELECT p.id AS member_id, p.username AS member_name, t.amount, t.ctime, t.mtime
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
        for take in nominal_takes:
            take['nominal_take'] = take.pop('amount')
            take['actual_amount'] = 0  # TODO
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
        members = OrderedDict()
        for take in takes.values():
            member = {}
            member['id'] = take['member_id']
            member['username'] = take['member_name']
            member['nominal_take'] = take['nominal_take']
            member['actual_amount'] = take['actual_amount']
            member['last_week'] = last_week = self.get_take_last_week_for(member)
            member['max_this_week'] = self.compute_max_this_week(last_week)
            members[member['id']] = member
        return members
