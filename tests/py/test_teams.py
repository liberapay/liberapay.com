from __future__ import unicode_literals

from liberapay.models._mixin_team import InactiveParticipantAdded
from liberapay.models.participant import Participant
from liberapay.testing import Harness


class Tests(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.a_team = self.make_participant('A-Team', kind='group')
        self.alice = self.make_participant('alice')
        self.a_team.add_member(self.alice)
        self.bob = self.make_participant('bob', email='bob@example.net')

    def test_member_of(self):
        actual = self.alice.member_of(self.a_team)
        assert actual is True

    def test_get_teams_for_member(self):
        b_team = self.make_participant('B-Team', kind='group')
        b_team.add_member(self.bob)
        actual = self.alice.get_teams().pop().nmembers
        assert actual == 1

    def test_preclude_adding_stub_participant(self):
        stub_participant = self.make_stub()
        with self.assertRaises(InactiveParticipantAdded):
            self.a_team.add_member(stub_participant)

    def test_remove_all_members(self):
        self.a_team.add_member(self.bob)
        assert len(self.a_team.get_current_takes()) == 2  # sanity check
        self.a_team.remove_all_members()
        assert len(self.a_team.get_current_takes()) == 0

    def test_invite_accept_leave(self):
        r = self.client.PxST(
            '/A-Team/membership/invite', {'username': 'bob'}, auth_as=self.alice,
        )
        assert r.code == 302

        r = self.client.PxST('/A-Team/membership/accept', auth_as=self.bob)
        assert r.code == 302
        is_member = self.bob.member_of(self.a_team)
        assert is_member is True

        r = self.client.PxST('/A-Team/membership/leave', auth_as=self.alice)
        assert r.code == 200
        assert 'confirm' in r.text

        r = self.client.PxST(
            '/A-Team/membership/leave', {'confirmed': 'true'}, auth_as=self.alice,
        )
        is_member = self.alice.member_of(self.a_team)
        assert is_member is False

    def test_refuse_invite(self):
        self.a_team.invite(self.bob, self.alice)
        r = self.client.PxST('/A-Team/membership/refuse', auth_as=self.bob)
        assert r.code == 302
        is_member = self.bob.member_of(self.a_team)
        assert is_member is False


class Tests2(Harness):

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
