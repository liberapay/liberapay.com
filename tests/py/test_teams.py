from __future__ import unicode_literals

from liberapay.models._mixin_team import InactiveParticipantAdded
from liberapay.models.participant import Participant
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.team = self.make_participant('A-Team', kind='group')

    def test_can_add_members(self):
        alice = self.make_participant('alice')
        expected = True
        self.team.add_member(alice)
        actual = alice.member_of(self.team)
        assert actual == expected

    def test_get_teams_for_member(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        team = self.make_participant('B-Team', kind='group')
        self.team.add_member(alice)
        team.add_member(bob)
        expected = 1
        actual = alice.get_teams().pop().nmembers
        assert actual == expected

    def test_preclude_adding_stub_participant(self):
        stub_participant = self.make_stub()
        with self.assertRaises(InactiveParticipantAdded):
            self.team.add_member(stub_participant)

    def test_remove_all_members(self):
        alice = self.make_participant('alice')
        self.team.add_member(alice)
        bob = self.make_participant('bob')
        self.team.add_member(bob)

        assert len(self.team.get_current_takes()) == 2  # sanity check
        self.team.remove_all_members()
        assert len(self.team.get_current_takes()) == 0

    def test_create_close_and_reopen_team(self):
        alice = self.make_participant('alice')
        r = self.client.PxST('/about/teams', {'name': 'Team'}, auth_as=alice)
        assert r.code == 302
        assert r.headers['Location'] == '/Team/edit'
        t = Participant.from_username('Team')
        assert t
        assert t.status == 'active'
        assert t.nmembers == 1

        t.close(None)
        t2 = t.refetch()
        assert t.status == t2.status == 'closed'
        assert t.goal == t2.goal == -1

        r = self.client.PxST('/about/teams', {'name': 'Team'}, auth_as=alice)
        assert r.code == 302
        assert r.headers['Location'] == '/Team/edit'
        t = t.refetch()
        assert t.nmembers == 1
        assert t.status == 'active'
        assert t.goal == None
