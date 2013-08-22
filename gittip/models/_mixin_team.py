"""Teams on Gittip are plural participants with members.
"""
from decimal import Decimal

from aspen.utils import typecheck


class MemberLimitReached(Exception): pass


class MixinTeam(object):
    """This class provides methods for working with a Participant as a Team.

    :param Participant participant: the underlying :py:class:`~gittip.participant.Participant` object for this team

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
        if not self.get_members():
            if self == user.participant:
                return True
            return False
        return True

    def add_member(self, member):
        """Add a member to this team.
        """
        assert self.IS_PLURAL
        if len(self.get_members()) == 149:
            raise MemberLimitReached
        self.__set_take_for(member, Decimal('0.01'), self)

    def remove_member(self, member):
        """Remove a member from this team.
        """
        assert self.IS_PLURAL
        self.__set_take_for(member, Decimal('0.00'), self)

    def member_of(self, team):
        """Given a Participant object, return a boolean.
        """
        assert team.IS_PLURAL
        for member in team.get_members():
            if member['username'] == self.username:
                return True
        return False

    def get_take_last_week_for(self, member):
        """What did the user actually take most recently? Used in throttling.
        """
        assert self.IS_PLURAL
        membername = member.username if hasattr(member, 'username') \
                                                        else member['username']
        return self.db.one("""

            SELECT amount
              FROM transfers
             WHERE tipper=%s AND tippee=%s
               AND timestamp >
                (SELECT ts_start FROM paydays ORDER BY ts_start DESC LIMIT 1)
          ORDER BY timestamp DESC LIMIT 1

        """, (self.username, membername), default=Decimal('0.00'))

    def get_take_for(self, member):
        """Return a Decimal representation of the take for this member, or 0.
        """
        assert self.IS_PLURAL
        return self.db.one( "SELECT take FROM current_memberships "
                            "WHERE member=%s AND team=%s"
                          , (member.username, self.username)
                          , default=Decimal('0.00')
                           )

    def compute_max_this_week(self, last_week):
        """2x last week's take, but at least a dollar.
        """
        return max(last_week * Decimal('2'), Decimal('1.00'))

    def set_take_for(self, member, take, recorder):
        """Sets member's take from the team pool.
        """
        assert self.IS_PLURAL

        # lazy import to avoid circular import
        from gittip.security.user import User
        from gittip.models.participant import Participant

        typecheck( member, Participant
                 , take, Decimal
                 , recorder, (Participant, User)
                  )

        last_week = self.get_take_last_week_for(member)
        max_this_week = self.compute_max_this_week(last_week)
        if take > max_this_week:
            take = max_this_week

        self.__set_take_for(member, take, recorder)
        return take

    def __set_take_for(self, member, take, recorder):
        assert self.IS_PLURAL
        # XXX Factored out for testing purposes only! :O Use .set_take_for.
        self.db.run("""

            INSERT INTO memberships (ctime, member, team, take, recorder)
             VALUES ( COALESCE (( SELECT ctime
                                    FROM memberships
                                   WHERE member=%s
                                     AND team=%s
                                   LIMIT 1
                                 ), CURRENT_TIMESTAMP)
                    , %s
                    , %s
                    , %s
                    , %s
                     )

        """, (member.username, self.username, member.username, self.username, \
                                                      take, recorder.username))

    def get_members(self):
        assert self.IS_PLURAL
        return self.db.all("""

            SELECT member AS username, take, ctime, mtime
              FROM current_memberships
             WHERE team=%s
          ORDER BY ctime DESC

        """, (self.username,), back_as=dict)

    def get_teams_membership(self):
        assert self.IS_PLURAL
        TAKE = "SELECT sum(take) FROM current_memberships WHERE team=%s"
        total_take = self.db.one(TAKE, (self.username,), default=0)
        team_take = max(self.get_dollars_receiving() - total_take, 0)
        membership = { "ctime": None
                     , "mtime": None
                     , "username": self.username
                     , "take": team_take
                      }
        return membership

    def get_memberships(self, current_participant):
        assert self.IS_PLURAL
        members = self.get_members()
        members.append(self.get_teams_membership())
        budget = balance = self.get_dollars_receiving()
        for member in members:
            member['removal_allowed'] = current_participant == self
            member['editing_allowed'] = False
            if current_participant is not None:
                if member['username'] == current_participant.username:
                    member['is_current_user'] = True
                    if member['ctime'] is not None:
                        # current user, but not the team itself
                        member['editing_allowed']= True
            take = member['take']
            member['take'] = take
            member['last_week'] = last_week = \
                                            self.get_take_last_week_for(member)
            member['max_this_week'] = self.compute_max_this_week(last_week)
            amount = min(take, balance)
            balance -= amount
            member['balance'] = balance
            member['percentage'] = (amount / budget) if budget > 0 else 0
        return members
