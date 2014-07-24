from __future__ import unicode_literals

from decimal import Decimal as D

from gittip.testing import Harness
from gittip.models.participant import Participant


TEAM = 'A Team'


class Tests(Harness):

    def make_team(self, username=TEAM, **kw):
        team = self.make_participant(username, number='plural', **kw)
        if Participant.from_username('Daddy Warbucks') is None:
            warbucks = self.make_participant( 'Daddy Warbucks'
                                            , claimed_time='now'
                                            , last_bill_result=''
                                             )
            self.warbucks = warbucks
        self.warbucks.set_tip_to(team, '100')
        return team

    def make_participant(self, username, **kw):
        take_last_week = kw.pop('take_last_week', None)
        team_name = kw.pop('', TEAM)
        participant = Harness.make_participant(self, username, **kw)
        if take_last_week is not None:
            if self.db.one('SELECT * FROM paydays') is None:
                self.db.run("INSERT INTO paydays DEFAULT VALUES")
            self.db.run( "INSERT INTO transfers (timestamp, tipper, tippee, amount, context) "
                         "VALUES (now(), %(tipper)s, %(tippee)s, %(amount)s, 'take')"
                       , dict(tipper=team_name, tippee=username, amount=take_last_week,)
                        )
            self.db.run("UPDATE paydays SET ts_end=now()")
        return participant

    def test_we_can_make_a_team(self):
        team = self.make_team()
        assert team.IS_PLURAL

    def test_random_schmoe_is_not_member_of_team(self):
        team = self.make_team()
        schmoe = self.make_participant('schmoe')
        assert not schmoe.member_of(team)

    def test_team_member_is_team_member(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='40.00', claimed_time='now')
        team.add_member(alice)
        assert alice.member_of(team)

    def test_cant_grow_tip_a_lot(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='40.00')
        team._MixinTeam__set_take_for(alice, D('40.00'), team)
        assert team.set_take_for(alice, D('100.00'), alice) == 80

    def test_take_can_double(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='40.00')
        team._MixinTeam__set_take_for(alice, D('40.00'), team)
        team.set_take_for(alice, D('80.00'), alice)
        assert team.get_take_for(alice) == 80

    def test_take_can_double_but_not_a_penny_more(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='40.00')
        team._MixinTeam__set_take_for(alice, D('40.00'), team)
        actual = team.set_take_for(alice, D('80.01'), alice)
        assert actual == 80

    def test_increase_is_based_on_actual_take_last_week(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='20.00')
        team._MixinTeam__set_take_for(alice, D('35.00'), team)
        assert team.set_take_for(alice, D('42.00'), alice) == 40

    def test_if_last_week_is_less_than_a_dollar_can_increase_to_a_dollar(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='0.01', claimed_time='now')
        team.add_member(alice)
        actual = team.set_take_for(alice, D('42.00'), team)
        assert actual == 1

    def test_get_members(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='40.00', claimed_time='now')
        team.add_member(alice)
        team.set_take_for(alice, D('42.00'), team)
        members = team.get_members(alice)
        assert len(members) == 2
        assert members[0]['username'] == 'alice'
        assert members[0]['take'] == 42
        assert members[0]['balance'] == 58

    def test_compute_actual_takes_counts_the_team_balance(self):
        team = self.make_team(balance=D('59.46'))
        alice = self.make_participant('alice', take_last_week='100.00', claimed_time='now')
        team.add_member(alice)
        team.set_take_for(alice, D('142.00'), team)
        takes = team.compute_actual_takes().values()
        assert len(takes) == 2
        assert takes[0]['member'] == 'alice'
        assert takes[0]['actual_amount'] == 142
        assert takes[0]['balance'] == D('17.46')
        assert takes[1]['member'] == TEAM
        assert takes[1]['actual_amount'] == 0
        assert takes[1]['balance'] == D('17.46')

    def test_compute_actual_takes_gives_correct_final_balance(self):
        team = self.make_team(balance=D('53.72'))
        alice = self.make_participant('alice', take_last_week='100.00', claimed_time='now')
        team.add_member(alice)
        team.set_take_for(alice, D('86.00'), team)
        takes = team.compute_actual_takes().values()
        assert len(takes) == 2
        assert takes[0]['member'] == 'alice'
        assert takes[0]['actual_amount'] == 86
        assert takes[0]['balance'] == D('67.72')
        assert takes[1]['member'] == TEAM
        assert takes[1]['actual_amount'] == 14
        assert takes[1]['balance'] == D('67.72')

    def test_taking_and_receiving_are_updated_correctly(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='40.00', claimed_time='now')
        team.add_member(alice)
        team.set_take_for(alice, D('42.00'), alice)
        assert alice.taking == 42
        assert alice.receiving == 42
        self.warbucks.set_tip_to(alice, D('10.00'))
        assert alice.taking == 42
        assert alice.receiving == 52
        team.set_take_for(alice, D('50.00'), alice)
        assert alice.taking == 50
        assert alice.receiving == 60

    def test_taking_is_zero_for_team(self):
        team = self.make_team()
        alice = self.make_participant('alice', claimed_time='now')
        team.add_member(alice)
        team = Participant.from_id(team.id)
        assert team.taking == 0
        assert team.receiving == 100

    def test_but_team_can_take_from_other_team(self):
        a_team = self.make_team('A Team', claimed_time='now')
        b_team = self.make_team('B Team', claimed_time='now')
        a_team.add_member(b_team)
        a_team.set_take_for(b_team, D('1.00'), b_team)

        b_team = Participant.from_id(b_team.id)
        assert b_team.taking == 1
        assert b_team.receiving == 101

    def test_changes_to_team_receiving_affect_members_take(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='40.00', claimed_time='now')
        team.add_member(alice)
        team.set_take_for(alice, D('42.00'), alice)

        self.warbucks.set_tip_to(team, D('10.00'))  # hard times
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 10

    def test_changes_to_others_take_affects_members_take(self):
        team = self.make_team()

        alice = self.make_participant('alice', take_last_week='30.00', claimed_time='now')
        team.add_member(alice)
        team.set_take_for(alice, D('42.00'), alice)

        bob = self.make_participant('bob', take_last_week='50.00', claimed_time='now')
        team.add_member(bob)
        team.set_take_for(bob, D('60.00'), bob)

        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 40

        # But get_members still uses nominal amount
        assert [m['take'] for m in  team.get_members(alice)] == [60, 42, 0]

    def test_changes_to_others_take_can_increase_members_take(self):
        team = self.make_team()

        alice = self.make_participant('alice', take_last_week='30.00', claimed_time='now')
        team.add_member(alice)
        team.set_take_for(alice, D('42.00'), alice)

        bob = self.make_participant('bob', take_last_week='60.00', claimed_time='now')
        team.add_member(bob)
        team.set_take_for(bob, D('80.00'), bob)
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 20

        team.set_take_for(bob, D('30.00'), bob)
        alice = Participant.from_username('alice')
        assert alice.receiving == alice.taking == 42

    # get_take_last_week_for - gtlwf

    def test_gtlwf_works_during_payday(self):
        team = self.make_team()
        alice = self.make_participant('alice', take_last_week='30.00', claimed_time='now')
        take_this_week = D('42.00')
        team.add_member(alice)
        team.set_take_for(alice, take_this_week, alice)
        self.db.run("INSERT INTO paydays DEFAULT VALUES")
        assert team.get_take_last_week_for(alice) == 30
        self.db.run("""
            INSERT INTO transfers (timestamp, tipper, tippee, amount, context)
            VALUES (now(), %(tipper)s, 'alice', %(amount)s, 'take')
        """, dict(tipper=team.username, amount=take_this_week))
        assert team.get_take_last_week_for(alice) == 30
