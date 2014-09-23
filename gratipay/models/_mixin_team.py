"""Teams on Gratipay are plural participants with members.
"""
from collections import OrderedDict
from decimal import Decimal

from aspen.utils import typecheck


class MemberLimitReached(Exception): pass

class StubParticipantAdded(Exception): pass

class MixinTeam(object):
    """This class provides methods for working with a Participant as a Team.

    :param Participant participant: the underlying :py:class:`~gratipay.participant.Participant` object for this team

    """

    # XXX These were all written with the ORM and need to be converted.

    def __init__(self, participant):
        self.participant = participant

    def show_as_team(self, user):
        """Return a boolean, whether to show this participant as a team.
        """
        if not self.IS_PLURAL:
            return False
        if user.ADMIN:
            return True
        if not self.get_current_takes():
            if self == user.participant:
                return True
            return False
        return True

    def add_member(self, member):
        """Add a member to this team.
        """
        assert self.IS_PLURAL
        if len(self.get_current_takes()) == 149:
            raise MemberLimitReached
        if not member.is_claimed:
            raise StubParticipantAdded
        self.__set_take_for(member, Decimal('0.01'), self)

    def remove_member(self, member):
        """Remove a member from this team.
        """
        assert self.IS_PLURAL
        self.__set_take_for(member, Decimal('0.00'), self)

    def remove_all_members(self, cursor=None):
        (cursor or self.db).run("""
            INSERT INTO takes (ctime, member, team, amount, recorder) (
                SELECT ctime, member, %(username)s, 0.00, %(username)s
                  FROM current_takes
                 WHERE team=%(username)s
                   AND amount > 0
            );
        """, dict(username=self.username))

    def member_of(self, team):
        """Given a Participant object, return a boolean.
        """
        assert team.IS_PLURAL
        for take in team.get_current_takes():
            if take['member'] == self.username:
                return True
        return False

    def get_take_last_week_for(self, member):
        """Get the user's nominal take last week. Used in throttling.
        """
        assert self.IS_PLURAL
        membername = member.username if hasattr(member, 'username') \
                                                        else member['username']
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

        """, (self.username, membername), default=Decimal('0.00'))

    def get_take_for(self, member):
        """Return a Decimal representation of the take for this member, or 0.
        """
        assert self.IS_PLURAL
        return self.db.one( "SELECT amount FROM current_takes "
                            "WHERE member=%s AND team=%s"
                          , (member.username, self.username)
                          , default=Decimal('0.00')
                           )

    def compute_max_this_week(self, last_week):
        """2x last week's take, but at least a dollar.
        """
        return max(last_week * Decimal('2'), Decimal('1.00'))

    def set_take_for(self, member, take, recorder, cursor=None):
        """Sets member's take from the team pool.
        """
        assert self.IS_PLURAL

        # lazy import to avoid circular import
        from gratipay.security.user import User
        from gratipay.models.participant import Participant

        typecheck( member, Participant
                 , take, Decimal
                 , recorder, (Participant, User)
                  )

        last_week = self.get_take_last_week_for(member)
        max_this_week = self.compute_max_this_week(last_week)
        if take > max_this_week:
            take = max_this_week

        self.__set_take_for(member, take, recorder, cursor)
        return take

    def __set_take_for(self, member, amount, recorder, cursor=None):
        assert self.IS_PLURAL
        # XXX Factored out for testing purposes only! :O Use .set_take_for.
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

            """, dict(member=member.username, team=self.username, amount=amount,
                      recorder=recorder.username))
            # Compute the new takes
            new_takes = self.compute_actual_takes(cursor)
            # Update receiving amounts in the participants table
            self.update_taking(old_takes, new_takes, cursor, member)

    def update_taking(self, old_takes, new_takes, cursor=None, member=None):
        """Update `taking` amounts based on the difference between `old_takes`
        and `new_takes`.
        """
        for username in set(old_takes.keys()).union(new_takes.keys()):
            if username == self.username:
                continue
            old = old_takes.get(username, {}).get('actual_amount', Decimal(0))
            new = new_takes.get(username, {}).get('actual_amount', Decimal(0))
            diff = new - old
            if diff != 0:
                r = (self.db or cursor).one("""
                    UPDATE participants
                       SET taking = (taking + %(diff)s)
                         , receiving = (receiving + %(diff)s)
                     WHERE username=%(username)s
                 RETURNING taking, receiving
                """, dict(username=username, diff=diff))
                if member and username == member.username:
                    member.set_attributes(**r._asdict())

    def get_current_takes(self, cursor=None):
        """Return a list of member takes for a team.
        """
        assert self.IS_PLURAL
        TAKES = """
            SELECT member, amount, ctime, mtime
              FROM current_takes
             WHERE team=%(team)s
          ORDER BY ctime DESC
        """
        records = (cursor or self.db).all(TAKES, dict(team=self.username))
        return [r._asdict() for r in records]

    def get_team_take(self, cursor=None):
        """Return a single take for a team, the team itself's take.
        """
        assert self.IS_PLURAL
        TAKE = "SELECT sum(amount) FROM current_takes WHERE team=%s"
        total_take = (cursor or self.db).one(TAKE, (self.username,), default=0)
        team_take = max(self.receiving - total_take, 0)
        membership = { "ctime": None
                     , "mtime": None
                     , "member": self.username
                     , "amount": team_take
                      }
        return membership

    def compute_actual_takes(self, cursor=None):
        """Get the takes, compute the actual amounts, and return an OrderedDict.
        """
        actual_takes = OrderedDict()
        nominal_takes = self.get_current_takes(cursor=cursor)
        nominal_takes.append(self.get_team_take(cursor=cursor))
        budget = balance = self.balance + self.receiving - self.giving
        for take in nominal_takes:
            nominal_amount = take['nominal_amount'] = take.pop('amount')
            actual_amount = take['actual_amount'] = min(nominal_amount, balance)
            if take['member'] != self.username:
                balance -= actual_amount
            take['balance'] = balance
            take['percentage'] = (actual_amount / budget) if budget > 0 else 0
            actual_takes[take['member']] = take
        return actual_takes

    def get_members(self, current_participant):
        """Return a list of member dicts.
        """
        assert self.IS_PLURAL
        takes = self.compute_actual_takes()
        members = []
        for take in takes.values():
            member = {}
            member['username'] = take['member']
            member['take'] = take['nominal_amount']
            member['balance'] = take['balance']
            member['percentage'] = take['percentage']

            member['removal_allowed'] = current_participant == self
            member['editing_allowed'] = False
            member['is_current_user'] = False
            if current_participant is not None:
                if member['username'] == current_participant.username:
                    member['is_current_user'] = True
                    if take['ctime'] is not None:
                        # current user, but not the team itself
                        member['editing_allowed']= True

            member['last_week'] = last_week = self.get_take_last_week_for(member)
            member['max_this_week'] = self.compute_max_this_week(last_week)
            members.append(member)
        return members
