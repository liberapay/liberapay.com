from __future__ import unicode_literals
import random
import datetime
from decimal import Decimal

import psycopg2
import pytz
from nose.tools import assert_raises

from gittip.testing import Harness
from gittip.models import Participant, Tip


class Tests(Harness):

    def setUp(self):
        super(Harness, self).setUp()
        self.team = self.make_participant('team1', 'plural')  # Our team

    def test_is_team(self):
        expeted = True
        actual = self.team.IS_PLURAL
        assert actual == expeted, actual

    # def test_show_as_team(self):
    #     expeted = True
    #     actual = self.team.show_as_team(self.team)
    #     assert actual == expected, actual

    def test_can_add_members(self):
        user = self.make_participant('user1')
        expected = True
        self.team.add_member(user)
        actual = user.member_of(self.team)
        assert actual == expected, actual

    def test_get_teams_for_member(self):
        user = self.make_participant('user1')
        user2 = self.make_participant('user2')
        team = self.make_participant('team2', 'plural')
        self.team.add_member(user)
        team.add_member(user2)
        expected = 1
        actual = user.get_teams().pop()['nmembers']
        assert actual == expected, actual
