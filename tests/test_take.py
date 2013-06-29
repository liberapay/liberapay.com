from decimal import Decimal as D

import gittip
from aspen.testing import assert_raises
from gittip.testing import Harness
from gittip.models.participant import Participant


class Tests(Harness):

    def make_team(self, name="Team"):
        team = self.make_participant(name)
        team.type = "open group"

        warbucks = self.make_participant('Daddy Warbucks')
        warbucks.last_bill_result = ''
        warbucks.set_tip_to('Team', '100')

        self.session.commit()
        return team

    def make_participant(self, username, *arg, **kw):
        participant = Harness.make_participant(self, username)
        if username == 'alice':
            take_last_week = kw.get('take_last_week', '40')
            gittip.db.execute("INSERT INTO paydays DEFAULT VALUES")
            gittip.db.execute( "INSERT INTO transfers "
                               "(timestamp, tipper, tippee, amount) "
                               "VALUES (now(), 'Team', 'alice', %s)"
                             , (take_last_week,)
                              )
        return participant

    def test_we_can_make_an_open_group(self):
        team = self.make_team()
        assert team.IS_OPEN_GROUP

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
        team._Participant__set_take_for(alice, D('40.00'))
        assert team.set_take_for(alice, D('100.00')) == 60

    def test_can_grow_tip_50_percent(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice')
        team._Participant__set_take_for(alice, D('40.00'))
        team.set_take_for(alice, D('60.00'))
        assert team.get_take_for(alice) == 60

    def test_can_grow_tip_50_percent_but_not_a_penny_more(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice')
        team._Participant__set_take_for(alice, D('40.00'))
        actual = team.set_take_for(alice, D('60.01'))
        assert actual == 60, actual

    def test_increase_is_based_on_actual_take_last_week(self):
        team = self.make_team('Team')
        alice = self.make_participant('alice', take_last_week='20.00')
        team._Participant__set_take_for(alice, D('40.00'))
        assert team.set_take_for(alice, D('42.00')) == 30

    def test_can_take_up_to_total_times_2_over_len_members(self):
        team = self.make_team('Team')
        team.add_member(self.make_participant('bob'))
        team.add_member(self.make_participant('charlie'))
        team.add_member(self.make_participant('diane'))
        team.add_member(self.make_participant('earl'))
        alice = self.make_participant('alice', take_last_week='38.00')
        team._Participant__set_take_for(alice, D('38.00'))
        team.set_take_for(alice, D('40.00'))
        assert team.get_take_for(alice) == 40

    def test_cant_take_more_than_blah_blah_blah(self):
        team = self.make_team('Team')
        team.add_member(self.make_participant('bob'))
        team.add_member(self.make_participant('charlie'))
        team.add_member(self.make_participant('diane'))
        team.add_member(self.make_participant('earl'))
        alice = self.make_participant('alice', take_last_week='38.00')
        team._Participant__set_take_for(alice, D('38.00'))
        team.set_take_for(alice, D('40.01'))
        assert team.get_take_for(alice) == 40
