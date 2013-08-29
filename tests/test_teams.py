from __future__ import unicode_literals

from gittip.testing import Harness
from gittip.security.user import User


class Tests(Harness):

    def setUp(self):
        super(Harness, self).setUp()
        self.team = self.make_participant('team1', number='plural')  # Our team

    def test_is_team(self):
        expeted = True
        actual = self.team.IS_PLURAL
        assert actual == expeted, actual

    def test_show_as_team_to_admin(self):
        self.make_participant('alice', is_admin=True)
        user = User.from_username('alice')
        assert self.team.show_as_team(user)

    def test_show_as_team_to_team_member(self):
        self.make_participant('alice')
        self.team.add_member(self.make_participant('bob'))
        user = User.from_username('bob')
        assert self.team.show_as_team(user)

    def test_show_as_team_to_non_team_member(self):
        self.make_participant('alice')
        self.team.add_member(self.make_participant('bob'))
        user = User.from_username('alice')
        assert self.team.show_as_team(user)

    def test_show_as_team_to_anon(self):
        self.make_participant('alice')
        self.team.add_member(self.make_participant('bob'))
        assert self.team.show_as_team(User())

    def test_dont_show_individuals_as_team(self):
        alice = self.make_participant('alice', number='singular')
        assert not alice.show_as_team(User())

    def test_dont_show_plural_no_members_as_team_to_anon(self):
        group = self.make_participant('Group', number='plural')
        assert not group.show_as_team(User())

    def test_dont_show_plural_no_members_as_team_to_auth(self):
        group = self.make_participant('Group', number='plural')
        self.make_participant('alice')
        assert not group.show_as_team(User.from_username('alice'))

    def test_show_plural_no_members_as_team_to_self(self):
        group = self.make_participant('Group', number='plural')
        assert group.show_as_team(User.from_username('Group'))

    def test_show_plural_no_members_as_team_to_admin(self):
        group = self.make_participant('Group', number='plural')
        self.make_participant('Admin', is_admin=True)
        assert group.show_as_team(User.from_username('Admin'))


    def test_can_add_members(self):
        user = self.make_participant('user1')
        expected = True
        self.team.add_member(user)
        actual = user.member_of(self.team)
        assert actual == expected, actual

    def test_get_teams_for_member(self):
        user = self.make_participant('user1')
        user2 = self.make_participant('user2')
        team = self.make_participant('team2', number='plural')
        self.team.add_member(user)
        team.add_member(user2)
        expected = 1
        actual = user.get_teams().pop().nmembers
        assert actual == expected, actual
