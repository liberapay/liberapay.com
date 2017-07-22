from __future__ import unicode_literals

from decimal import Decimal as D

from psycopg2 import InternalError

from liberapay.billing.payday import Payday
from liberapay.testing import Harness
from liberapay.models.participant import Participant


TEAM = 'A Team'


class Tests(Harness):

    def make_team(self, username=TEAM, **kw):
        team = self.make_participant(username, kind='group', **kw)
        if Participant.from_username('Daddy Warbucks') is None:
            self.warbucks = self.make_participant('Daddy Warbucks', balance=1000)
        self.warbucks.set_tip_to(team, '100')
        return team

    def make_team_of_one(self, username=TEAM, **kw):
        team = self.make_team(username=username, **kw)
        alice = self.make_team_member(team, 'alice')
        return team, alice

    def make_team_of_two(self, username=TEAM, **kw):
        team, alice = self.make_team_of_one(username=username, **kw)
        bob = self.make_team_member(team, 'bob')
        return team, alice, bob

    def make_team_member(self, team, username, **kw):
        user = self.make_participant(username, **kw)
        team.add_member(user)
        return user

    def take_last_week(self, team, member, amount, actual_amount=None):
        team.set_take_for(member, amount, team, check_max=False)
        Payday.start()
        actual_amount = amount if actual_amount is None else actual_amount
        if D(actual_amount) > 0:
            self.db.run("""
                INSERT INTO transfers (tipper, tippee, amount, context, status, team, wallet_from, wallet_to)
                VALUES (%(tipper)s, %(tippee)s, %(amount)s, 'take', 'succeeded', %(team)s, '-1', '-2')
            """, dict(tipper=self.warbucks.id, tippee=member.id, amount=actual_amount, team=team.id))
        self.db.run("UPDATE paydays SET ts_end=now() WHERE ts_end < ts_start")

    def test_random_schmoe_is_not_member_of_team(self):
        team = self.make_team()
        schmoe = self.make_participant('schmoe')
        assert not schmoe.member_of(team)

    def test_team_member_is_team_member(self):
        team, alice = self.make_team_of_one()
        assert alice.member_of(team)

    def test_can_take_any_amount_when_there_is_only_one_member(self):
        team, alice = self.make_team_of_one()
        self.take_last_week(team, alice, '0.44')
        team.set_take_for(alice, D('333.33'), alice)
        assert team.get_take_for(alice) == D('333.33')

    def test_take_can_double(self):
        team, alice, bob = self.make_team_of_two()
        self.take_last_week(team, alice, '40.00')
        team.set_take_for(alice, D('80.00'), alice)
        assert team.get_take_for(alice) == 80

    def test_take_can_double_but_not_a_penny_more(self):
        team, alice, bob = self.make_team_of_two()
        self.warbucks.set_tip_to(team, '20')
        self.take_last_week(team, alice, '40.00')
        actual = team.set_take_for(alice, D('80.01'), alice)
        assert actual == 80

    def test_increase_is_based_on_nominal_take_last_week(self):
        team, alice, bob = self.make_team_of_two()
        self.warbucks.set_tip_to(team, '15.03')
        self.take_last_week(team, alice, '20.00', actual_amount='15.03')
        team.set_take_for(alice, D('35.00'), team, check_max=False)
        assert team.set_take_for(alice, D('42.00'), alice) == 40

    def test_if_last_week_is_less_than_one_can_increase_to_one(self):
        team, alice, bob = self.make_team_of_two()
        self.warbucks.set_tip_to(team, '0.50')
        self.take_last_week(team, alice, '0.01')
        actual = team.set_take_for(alice, D('42.00'), team)
        assert actual == 1

    def test_can_take_any_amount_when_takes_were_all_zero_last_week(self):
        team, alice, bob = self.make_team_of_two()
        self.take_last_week(team, alice, '0.00')
        self.take_last_week(team, bob, '0.00')
        actual = team.set_take_for(alice, D('222.00'), team)
        assert actual == 222

    def test_can_take_leftover(self):
        team, alice, bob = self.make_team_of_two()
        self.take_last_week(team, alice, '0.01')
        actual = team.set_take_for(alice, D('200.00'), team)
        assert actual == 100

    def test_can_take_any_amount_when_throttling_is_disabled(self):
        team, alice, bob = self.make_team_of_two(throttle_takes=False)
        self.take_last_week(team, alice, '0.00')
        team.set_take_for(alice, D('400.00'), alice)
        assert team.get_take_for(alice) == 400
        self.take_last_week(team, alice, '10.00')
        team.set_take_for(alice, D('500.00'), alice)
        assert team.get_take_for(alice) == 500

    def test_get_members(self):
        team, alice = self.make_team_of_one()
        self.take_last_week(team, alice, '40.00')
        team.set_take_for(alice, D('42.00'), team)
        members = team.get_members()
        assert len(members) == 1
        assert members[alice.id]['username'] == 'alice'
        assert members[alice.id]['nominal_take'] == 42
        assert members[alice.id]['actual_amount'] == 42

    def test_taking_and_receiving_are_updated_correctly(self):
        team, alice = self.make_team_of_one()
        self.take_last_week(team, alice, '40.00')
        self.warbucks.set_tip_to(team, D('42.00'))
        team.set_take_for(alice, D('42.00'), alice)
        assert alice.taking == 42
        assert alice.receiving == 42
        self.warbucks.set_tip_to(alice, D('10.00'))
        assert alice.taking == 42
        assert alice.receiving == 52
        self.warbucks.set_tip_to(team, D('50.00'))
        assert team.receiving == 50
        team.set_take_for(alice, D('50.00'), alice)
        assert alice.taking == 50
        assert alice.receiving == 60

    def test_taking_is_zero_for_team(self):
        team, alice = self.make_team_of_one()
        team.add_member(alice)
        team = Participant.from_id(team.id)
        assert team.taking == 0
        assert team.receiving == 100

    def test_team_cant_take_from_other_team(self):
        a_team = self.make_team('A Team')
        b_team = self.make_team('B Team')
        with self.assertRaises(InternalError):
            a_team.add_member(b_team)

    def test_changes_to_team_receiving_affect_members_take(self):
        team, alice = self.make_team_of_one()
        self.take_last_week(team, alice, '40.00')
        team.set_take_for(alice, D('42.00'), alice)

        self.warbucks.set_tip_to(team, D('10.00'))  # hard times
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 10

    def test_changes_to_others_take_affects_members_take(self):
        team, alice, bob = self.make_team_of_two()

        self.take_last_week(team, alice, '30.00')
        team.set_take_for(alice, D('40.00'), alice)

        self.take_last_week(team, bob, '50.00')
        team.set_take_for(bob, D('60.00'), bob)

        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 40

        for m in team.get_members().values():
            assert m['nominal_take'] == m['actual_amount']

    def test_changes_to_others_take_can_increase_members_take(self):
        team, alice, bob = self.make_team_of_two()

        self.take_last_week(team, alice, '30.00')
        team.set_take_for(alice, D('25.00'), alice)

        self.take_last_week(team, bob, '50.00')
        team.set_take_for(bob, D('100.00'), bob)
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 20

        team.set_take_for(bob, D('75.00'), bob)
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 25

    # get_takes_last_week - gtlw

    def test_gtlwf_works_during_payday(self):
        team, alice = self.make_team_of_one()
        self.take_last_week(team, alice, '20.00')
        assert team.get_takes_last_week()[alice.id] == 20
        self.take_last_week(team, alice, '30.00')
        assert team.get_takes_last_week()[alice.id] == 30
        take_this_week = D('42.00')
        team.set_take_for(alice, take_this_week, alice)
        Payday.start()
        assert team.get_takes_last_week()[alice.id] == 30
        self.db.run("""
            INSERT INTO transfers (tipper, tippee, amount, context, status, team, wallet_from, wallet_to)
            VALUES (%(tipper)s, %(id)s, %(amount)s, 'take', 'succeeded', %(team)s, '-1', '-2')
        """, dict(tipper=self.warbucks.id, id=alice.id, amount=take_this_week, team=team.id))
        assert team.get_takes_last_week()[alice.id] == 30
