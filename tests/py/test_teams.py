from liberapay.exceptions import EmailAlreadyAttachedToSelf, EmailAlreadyTaken
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

    def test_invite_is_scoped_to_specific_team(self):
        b_team = self.make_participant('B-Team', kind='group')
        self.a_team.invite(self.bob, self.alice)

        # Check that bob can't use the invite from A-Team to join B-Team
        r = self.client.PxST('/B-Team/membership/accept', auth_as=self.bob)
        assert r.code == 403
        assert 'not invited' in r.text
        is_member = self.bob.member_of(b_team)
        assert is_member is False

    def test_members_can_take_from_team(self):
        r = self.client.PxST('/A-Team/income/take', {'take': '1'}, auth_as=self.alice)
        assert r.code == 302
        take = self.a_team.get_take_for(self.alice)
        assert take == 1

    def test_non_members_cant_take_from_team(self):
        r = self.client.PxST('/A-Team/income/take', {'take': '2'}, auth_as=self.bob)
        assert r.code == 403
        take = self.a_team.get_take_for(self.bob)
        assert take is None


class Tests2(Harness):

    def test_create_close_and_reopen_team(self):
        alice = self.make_participant('alice')
        r = self.client.PxST('/about/teams', {'name': 'Team'}, auth_as=alice)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/Team/edit'
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
        assert r.headers[b'Location'] == b'/Team/edit'
        t = t.refetch()
        assert t.nmembers == 1
        assert t.status == 'active'
        assert t.goal == None

    def test_create_team_with_verified_email(self):
        alice = self.make_participant('alice')
        email = 'bob@example.org'
        self.make_participant('bob', email=email)
        data = {'name': 'Team', 'email': email}
        r = self.client.PxST('/about/teams', data, auth_as=alice)
        assert r.code == 409
        assert isinstance(r, EmailAlreadyTaken)

    def test_create_team_with_same_unverified_email_as_creator(self):
        alice = self.make_participant('alice')
        email = 'alice@example.com'
        alice.add_email(email)
        data = {'name': 'Team', 'email': email}
        r = self.client.PxST('/about/teams', data, auth_as=alice)
        assert r.code == 409
        assert isinstance(r, EmailAlreadyAttachedToSelf)
        t = Participant.from_username('Team')
        assert not t

    def test_payment_providers_of_team(self):
        # 1. Test when the creator doesn't have any connected payment account.
        alice = self.make_participant('alice')
        data = {'name': 'Team1'}
        r = self.client.PxST('/about/teams', data, auth_as=alice)
        assert r.code == 302
        team = Participant.from_username(data['name'])
        assert team.payment_providers == 0

        # 2. Test when the creator has connected a PayPal account.
        self.add_payment_account(alice, 'paypal')
        data = {'name': 'Team2'}
        r = self.client.PxST('/about/teams', data, auth_as=alice)
        assert r.code == 302
        team = Participant.from_username(data['name'])
        assert team.payment_providers == 2

        # 3. Test after adding a member with a connected Stripe account.
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        team.add_member(bob)
        team = team.refetch()
        assert team.payment_providers == 3

        # 4. Test after the creator leaves.
        team.set_take_for(alice, None, alice)
        team = team.refetch()
        assert team.payment_providers == 1
