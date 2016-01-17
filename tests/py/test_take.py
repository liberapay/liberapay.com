from __future__ import unicode_literals

from decimal import Decimal as D

from psycopg2 import InternalError

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

    def take_last_week(self, team, member, amount, actual_amount=None):
        team.set_take_for(member, amount, member, check_max=False)
        self.db.run("INSERT INTO paydays DEFAULT VALUES")
        actual_amount = amount if actual_amount is None else actual_amount
        self.db.run("""
            INSERT INTO transfers (tipper, tippee, amount, context, status, team)
            VALUES (%(tipper)s, %(tippee)s, %(amount)s, 'take', 'succeeded', %(team)s)
        """, dict(tipper=self.warbucks.id, tippee=member.id, amount=actual_amount, team=team.id))
        self.db.run("UPDATE paydays SET ts_end=now() WHERE ts_end < ts_start")

    def test_random_schmoe_is_not_member_of_team(self):
        team = self.make_team()
        schmoe = self.make_participant('schmoe')
        assert not schmoe.member_of(team)

    def test_team_member_is_team_member(self):
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '40.00')
        assert alice.member_of(team)

    def test_cant_grow_tip_a_lot(self):
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '40.00')
        assert team.set_take_for(alice, D('100.00'), alice) == 80

    def test_take_can_double(self):
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '40.00')
        team.set_take_for(alice, D('80.00'), alice)
        assert team.get_take_for(alice) == 80

    def test_take_can_double_but_not_a_penny_more(self):
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '40.00')
        actual = team.set_take_for(alice, D('80.01'), alice)
        assert actual == 80

    def test_increase_is_based_on_nominal_take_last_week(self):
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '20.00', actual_amount='15.03')
        team.set_take_for(alice, D('35.00'), team, check_max=False)
        assert team.set_take_for(alice, D('42.00'), alice) == 40

    def test_if_last_week_is_less_than_one_can_increase_to_one(self):
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '0.01')
        actual = team.set_take_for(alice, D('42.00'), team)
        assert actual == 1

    def test_get_members(self):
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '40.00')
        team.set_take_for(alice, D('42.00'), team)
        members = team.get_members()
        assert len(members) == 1
        assert members[alice.id]['username'] == 'alice'
        assert members[alice.id]['nominal_take'] == 42

    def test_taking_and_receiving_are_updated_correctly(self):
        team = self.make_team()
        alice = self.make_participant('alice')
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
        team = self.make_team()
        alice = self.make_participant('alice')
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
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '40.00')
        team.set_take_for(alice, D('42.00'), alice)

        self.warbucks.set_tip_to(team, D('10.00'))  # hard times
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 10

    def test_changes_to_others_take_affects_members_take(self):
        team = self.make_team()

        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '30.00')
        team.set_take_for(alice, D('40.00'), alice)

        bob = self.make_participant('bob')
        self.take_last_week(team, bob, '50.00')
        team.set_take_for(bob, D('60.00'), bob)

        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 40

        for m in team.get_members().values():
            assert m['nominal_take'] == m['actual_amount']

    def test_changes_to_others_take_can_increase_members_take(self):
        team = self.make_team()

        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '30.00')
        team.set_take_for(alice, D('25.00'), alice)

        bob = self.make_participant('bob')
        self.take_last_week(team, bob, '50.00')
        team.set_take_for(bob, D('100.00'), bob)
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 20

        team.set_take_for(bob, D('75.00'), bob)
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 25

    # get_takes_last_week - gtlw

    def test_gtlwf_works_during_payday(self):
        team = self.make_team()
        alice = self.make_participant('alice')
        self.take_last_week(team, alice, '30.00')
        take_this_week = D('42.00')
        team.set_take_for(alice, take_this_week, alice)
        self.db.run("INSERT INTO paydays DEFAULT VALUES")
        assert team.get_takes_last_week()[alice.id] == 30
        self.db.run("""
            INSERT INTO transfers (tipper, tippee, amount, context, status, team)
            VALUES (%(tipper)s, %(id)s, %(amount)s, 'take', 'succeeded', %(team)s)
        """, dict(tipper=self.warbucks.id, id=alice.id, amount=take_this_week, team=team.id))
        assert team.get_takes_last_week()[alice.id] == 30
