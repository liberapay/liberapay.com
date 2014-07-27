from __future__ import print_function, unicode_literals

import json
from decimal import Decimal

from gittip.testing import Harness


class Tests(Harness):

    def setUp(self):
        self.make_participant('alice', claimed_time='now')

    def change_goal(self, goal, goal_custom="", auth_as="alice", expecting_error=False):
        method = self.client.POST if not expecting_error else self.client.PxST
        response = method( "/alice/goal.json"
                         , {'goal': goal, 'goal_custom': goal_custom}
                         , auth_as=auth_as
                          )
        return response


    def test_participant_can_set_their_goal_to_null(self):
        response = self.change_goal("null")
        actual = json.loads(response.body)['goal']
        assert actual == None

    def test_participant_can_set_their_goal_to_zero(self):
        response = self.change_goal("0")
        actual = json.loads(response.body)['goal']
        assert actual == "0"

    def test_participant_can_set_their_goal_to_a_custom_amount(self):
        response = self.change_goal("custom", "100.00")
        actual = json.loads(response.body)['goal']
        assert actual == "100"

    def test_custom_amounts_can_include_comma(self):
        response = self.change_goal("custom", "1,100.00")
        actual = json.loads(response.body)['goal']
        assert actual == "1,100"

    def test_wonky_custom_amounts_are_standardized(self):
        response = self.change_goal("custom", ",100,100.00000")
        actual = json.loads(response.body)['goal']
        assert actual == "100,100"

    def test_anonymous_gets_404(self):
        response = self.change_goal("100.00", auth_as=None, expecting_error=True)
        assert response.code == 404, response.code

    def test_invalid_is_400(self):
        response = self.change_goal("cheese", expecting_error=True)
        assert response.code == 400, response.code

    def test_invalid_custom_amount_is_400(self):
        response = self.change_goal("custom", "cheese", expecting_error=True)
        assert response.code == 400, response.code


    # Exercise the event logging for goal changes.

    def test_last_goal_is_stored_in_participants_table(self):
        self.change_goal("custom", "100")
        self.change_goal("custom", "200")
        self.change_goal("custom", "300")
        self.change_goal("null", "")
        self.change_goal("custom", "400")
        actual = self.db.one("SELECT goal FROM participants")
        assert actual == Decimal("400.00")

    def test_all_goals_are_stored_in_events_table(self):
        self.change_goal("custom", "100")
        self.change_goal("custom", "200")
        self.change_goal("custom", "300")
        self.change_goal("null", "")
        self.change_goal("custom", "400")
        actual = self.db.all("""
            SELECT (payload->'values'->>'goal')::int AS goal
              FROM events
             WHERE 'goal' IN (SELECT json_object_keys(payload->'values'))
          ORDER BY ts DESC
        """)
        assert actual == [400, None, 300, 200, 100]
