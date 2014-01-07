from __future__ import unicode_literals

from decimal import Decimal as D

from gittip.testing import Harness


class Tests(Harness):

    def make_team(self, name="Team"):
        team = self.make_participant(name, number='plural')

        warbucks = self.make_participant( 'Daddy Warbucks'
                                        , last_bill_result=''
                                         )
        warbucks.set_tip_to('Team', '100')

        return team

    def make_participant(self, username, *arg, **kw):
        take_last_week = kw.pop('take_last_week', '40')
        participant = Harness.make_participant(self, username, **kw)
        if username == 'alice':
            self.db.run("INSERT INTO paydays DEFAULT VALUES")
            self.db.run( "INSERT INTO transfers "
                           "(timestamp, tipper, tippee, amount) "
                           "VALUES (now(), 'Team', 'alice', %s)"
                         , (take_last_week,)
                          )
        return participant

    def test_we_can_make_a_team(self):
        team = self.make_team()
        assert team.IS_PLURAL

    def test_random_schmoe_is_not_member_of_team(self):
        team = self.make_team('Team')
        schmoe = self.make_participant('schmoe')
        assert not schmoe.member_of(team)

    def test_team_member_is_team_member(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice')
        team.add_member(alice)
        assert alice.member_of(team)

    def test_cant_grow_tip_a_lot(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice')
        team._MixinTeam__set_take_for(alice, D('40.00'), team)
        assert team.set_take_for(alice, D('100.00'), alice) == 80

    def test_take_can_double(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice')
        team._MixinTeam__set_take_for(alice, D('40.00'), team)
        team.set_take_for(alice, D('80.00'), alice)
        assert team.get_take_for(alice) == 80

    def test_take_can_double_but_not_a_penny_more(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice')
        team._MixinTeam__set_take_for(alice, D('40.00'), team)
        actual = team.set_take_for(alice, D('80.01'), alice)
        assert actual == 80

    def test_increase_is_based_on_actual_take_last_week(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice', take_last_week='20.00')
        team._MixinTeam__set_take_for(alice, D('35.00'), team)
        assert team.set_take_for(alice, D('42.00'), alice) == 40

    def test_if_last_week_is_less_than_a_dollar_can_increase_to_a_dollar(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice', take_last_week='0.01')
        team.add_member(alice)
        actual = team.set_take_for(alice, D('42.00'), team)
        assert actual == 1
